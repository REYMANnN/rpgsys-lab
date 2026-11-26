"""G10: a pista da AMA bate bit a bit com a referência e aproxima a atenção real."""
import math
import random

from amaranth.sim import Simulator

from rtl.ama_pista import AmaPista, referencia, D, F

ESC, DESL = 23, 8   # escala ~ log2(e)/sqrt(8) em Q8 -> 0,51 * 2^8 / 2^8 ... ajustado p/ F=8: (dot*23)>>8 ~ dot*0.09 em log2 x2^8


def rodar_rtl(casos):
    dut = AmaPista()
    saidas = []

    async def tb(ctx):
        for q, ks, vs in casos:
            ctx.set(dut.carrega_q, 1)
            for i in range(D):
                ctx.set(dut.q[i], q[i])
            ctx.set(dut.escala, ESC)
            ctx.set(dut.desloc, DESL)
            await ctx.tick()
            ctx.set(dut.carrega_q, 0)
            ctx.set(dut.valido, 1)
            for k, v in zip(ks, vs):
                for i in range(D):
                    ctx.set(dut.k[i], k[i])
                    ctx.set(dut.v[i], v[i])
                await ctx.tick()
            ctx.set(dut.valido, 0)
            saidas.append((ctx.get(dut.m), ctx.get(dut.l), [ctx.get(dut.o[i]) for i in range(D)]))

    sim = Simulator(dut)
    sim.add_clock(1e-9)
    sim.add_testbench(tb)
    sim.run()
    return saidas


def casos(n, seed, tmin=1, tmax=64):
    r = random.Random(seed)
    out = []
    for _ in range(n):
        T = r.randint(tmin, tmax)
        q = [r.randint(-128, 127) for _ in range(D)]
        ks = [[r.randint(-128, 127) for _ in range(D)] for _ in range(T)]
        vs = [[r.randint(-128, 127) for _ in range(D)] for _ in range(T)]
        out.append((q, ks, vs))
    return out


def test_bit_a_bit():
    cs = casos(150, 1)
    # inclui casos extremos: tudo máximo, tudo mínimo, escores iguais
    cs.append(([127] * D, [[127] * D] * 40, [[127] * D] * 40))
    cs.append(([-128] * D, [[127] * D] * 40, [[-128] * D] * 40))
    cs.append(([0] * D, [[5] * D] * 64, [[-7] * D] * 64))
    for (q, ks, vs), (m, l, o) in zip(cs, rodar_rtl(cs)):
        assert (m, l, o) == referencia(q, ks, vs, ESC, DESL)


def test_precisao_contra_atencao_real():
    erros = []
    for q, ks, vs in casos(300, 2, 16, 256):
        m, l, o = referencia(q, ks, vs, ESC, DESL)
        sc = [sum(a * b for a, b in zip(q, k)) * ESC / 2 ** DESL / 2 ** F for k in ks]   # em log2
        mx = max(sc)
        w = [2 ** (s - mx) for s in sc]
        Z = sum(w)
        ref = [sum(wi * v[i] for wi, v in zip(w, vs)) / Z for i in range(D)]
        hw = [oi / l for oi in o]
        erros.append(max(abs(a - b) for a, b in zip(ref, hw)) / 255)   # erro relativo à faixa do int8
    erros.sort()
    p99 = erros[int(0.99 * len(erros))]
    assert p99 < 0.01, p99   # < 1% da faixa: abaixo do erro de quantizar V em int8 (0,4%) x 2,5
