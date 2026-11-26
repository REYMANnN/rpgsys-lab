"""Verificação formal limitada (BMC, 8 ciclos a partir do reset, SymbiYosys + z3) da pista da AMA.
Todas as entradas são livres (qualquer q, k, v, escala, recarga e reset em qualquer ciclo).
Pendente: prova ilimitada (k-indução) — ver LICOES L11.

P1  depois do 1º token, l >= 2^16           (a normalização O/l nunca divide por ~0)
P2  l <= cnt * 2^16                          (com cnt < 2^24 tokens, l < 2^40: sem estouro)
P3  m nunca diminui entre tokens             (o máximo do softmax é monotônico)
Usa D=2 (os elementos são independentes; P1–P3 não dependem de D).
"""
import subprocess
import sys
from pathlib import Path

from amaranth import Module, Signal, unsigned, signed
from amaranth.hdl import Assert, Assume
from amaranth.back import rtlil

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from rtl.ama_pista import AmaPista  # noqa: E402

AQUI = Path(__file__).resolve().parent


def harness():
    m = Module()
    m.submodules.dut = dut = AmaPista(d=2)
    cnt = Signal(unsigned(25))
    m_ant = Signal(signed(32))
    vazio_ant = Signal(init=1)
    with m.If(dut.carrega_q):
        m.d.sync += cnt.eq(0)
    with m.Elif(dut.valido):
        m.d.sync += cnt.eq(cnt + 1)
    m.d.sync += [m_ant.eq(dut.m), vazio_ant.eq(dut.vazio)]
    m.d.comb += Assume(cnt < (1 << 24))
    m.d.comb += Assume(dut.desloc >= 4)
    m.d.comb += Assert(dut.vazio | (dut.l >= (1 << 16)))
    m.d.comb += Assert(dut.l <= (cnt << 16))
    m.d.comb += Assert(dut.vazio | vazio_ant | (dut.m >= m_ant))
    # ligação estado do harness <-> estado do dut (invariante de indução)
    m.d.comb += Assert(dut.vazio == (cnt == 0))
    return m, dut


if __name__ == "__main__":
    m, dut = harness()
    portas = [dut.carrega_q, dut.escala, dut.desloc, dut.valido, *dut.q, *dut.k, *dut.v]
    (AQUI / "ama.il").write_text(rtlil.convert(m, ports=portas))
    (AQUI / "ama.sby").write_text("""[options]
mode bmc
depth 8

[engines]
smtbmc z3

[script]
read_rtlil ama.il
prep -top top

[files]
ama.il
""")
    import os
    env = dict(os.environ, PATH=f"{AQUI / 'bin'}:{os.environ['PATH']}")
    r = subprocess.run(["yowasp-sby", "-f", "ama.sby"], cwd=AQUI, capture_output=True, text=True, env=env)
    print(r.stdout[-1500:])
    sys.exit(0 if "DONE (PASS" in r.stdout else 1)
