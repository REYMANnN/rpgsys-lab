"""Pista de atenção da AMA (bloco crítico do base die) — RTL em Amaranth.

Um ciclo por token de contexto. Para uma consulta q (D x int8) já carregada, recebe (k, v) (D x int8)
e mantém o estado do softmax em linha:
  m  = maior escore visto (ponto fixo, F bits de fração, unidade log2)
  l  = soma de 2^(s - m)                       (Q16)
  O  = soma de 2^(s - m) * v                   (Q16 x int8)
A normalização final O / l é feita pelo chip de cálculo (uma divisão por consulta, fora do laço).
Exponencial: 2^-d = 2^-int(d) * 2^-frac(d), com tabela de 2^LUT entradas (Q16).
"""
from __future__ import annotations

from amaranth import Module, Signal, signed, unsigned, Mux, Cat, Array, Const
from amaranth.lib import wiring
from amaranth.lib.wiring import In, Out

D = 8          # elementos por vetor
F = 8          # bits de fração do escore em log2
LUT = 6        # bits de fração usados na tabela
Q = 16         # Q16 para probabilidades


def tabela():
    return [round(2 ** (-(i / 2 ** LUT)) * (1 << Q)) for i in range(2 ** LUT)]


class AmaPista(wiring.Component):
    def __init__(self, d=D):
        self.d = d
        super().__init__({
            "carrega_q": In(1), "q": In(signed(8)).array(d), "escala": In(unsigned(16)), "desloc": In(unsigned(5)),
            "valido": In(1), "k": In(signed(8)).array(d), "v": In(signed(8)).array(d),
            "m": Out(signed(32)), "l": Out(unsigned(40)), "o": Out(signed(48)).array(d), "vazio": Out(1),
        })

    def elaborate(self, platform):
        mod = Module()
        d = self.d
        qreg = Array(Signal(signed(8), name=f"q{i}") for i in range(d))
        m = Signal(signed(32))
        l = Signal(unsigned(40))  # 32 bits estourava acima de 65.536 tokens iguais (achado na revisão)
        o = Array(Signal(signed(48), name=f"o{i}") for i in range(d))
        vazio = Signal(init=1)

        # escore: produto interno -> escala (log2(e)/sqrt(dh) em ponto fixo) -> F bits de fração
        dot = Signal(signed(24))
        mod.d.comb += dot.eq(sum(qreg[i] * self.k[i] for i in range(d)))
        s = Signal(signed(32))
        mod.d.comb += s.eq((dot * self.escala) >> self.desloc)

        m_novo = Signal(signed(32))
        mod.d.comb += m_novo.eq(Mux(vazio | (s > m), s, m))

        def exp2neg(delta, nome):
            """2^-(delta / 2^F) em Q16, delta >= 0."""
            ip = Signal(unsigned(24), name=f"{nome}_ip")
            fr = Signal(unsigned(LUT), name=f"{nome}_fr")
            r = Signal(unsigned(Q + 1), name=f"{nome}_r")
            t = Signal(unsigned(Q + 1), name=f"{nome}_lut")
            # tabela como lógica combinacional (case), não como memória: na prova formal uma ROM vira
            # estado livre e o solver pode inventar o conteúdo (achado na indução, L9)
            with mod.Switch(fr):
                for i, x in enumerate(tabela()):
                    with mod.Case(i):
                        mod.d.comb += t.eq(x)
            mod.d.comb += [ip.eq(delta >> F), fr.eq(delta[F - LUT:F]), r.eq(Mux(ip > Q, 0, t >> ip))]
            return r

        da = Signal(unsigned(32))
        db = Signal(unsigned(32))
        mod.d.comb += [da.eq(m_novo - m), db.eq(m_novo - s)]
        a = exp2neg(da, "a")     # fator de reescala do estado antigo
        b = exp2neg(db, "b")     # peso do token novo

        with mod.If(self.carrega_q):
            for i in range(d):
                mod.d.sync += qreg[i].eq(self.q[i])
            mod.d.sync += [vazio.eq(1), m.eq(0), l.eq(0)] + [o[i].eq(0) for i in range(d)]
        with mod.Elif(self.valido):
            mod.d.sync += [vazio.eq(0), m.eq(m_novo)]
            with mod.If(vazio):
                mod.d.sync += l.eq(1 << Q)
                for i in range(d):
                    mod.d.sync += o[i].eq(self.v[i] << Q)
            with mod.Else():
                mod.d.sync += l.eq(((l * a) >> Q) + b)
                for i in range(d):
                    mod.d.sync += o[i].eq(((o[i] * a) >> Q) + b * self.v[i])

        mod.d.comb += [self.m.eq(m), self.l.eq(l), self.vazio.eq(vazio)] + [self.o[i].eq(o[i]) for i in range(d)]
        return mod


def referencia(q, ks, vs, escala, desloc):
    """Modelo de referência bit a bit (mesma aritmética inteira do RTL)."""
    T = tabela()

    def e2(delta):
        ip, fr = delta >> F, (delta >> (F - LUT)) & (2 ** LUT - 1)
        return 0 if ip > Q else T[fr] >> ip
    m = l = 0
    o = [0] * len(q)
    vazio = True
    for k, v in zip(ks, vs):
        dot = sum(a * b for a, b in zip(q, k))
        s = (dot * escala) >> desloc
        mn = s if (vazio or s > m) else m
        if vazio:
            l, o = 1 << Q, [x << Q for x in v]
        else:
            a, b = e2(mn - m), e2(mn - s)
            l = ((l * a) >> Q) + b
            o = [((oi * a) >> Q) + b * vi for oi, vi in zip(o, v)]
        m, vazio = mn, False
    return m, l, o
