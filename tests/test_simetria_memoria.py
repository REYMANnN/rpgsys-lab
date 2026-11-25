from jobs import c003
from lab.params import load


def test_memoria_cara_encarece_gpus():
    P, C = load("params.yaml"), load("competitors.yaml")
    ref = c003.nominais_mem(P)
    p = c003.params(P)
    base = {g.nome: g.preco_usd for g in c003.gpus(C, p, ref)}
    p2 = dict(p, hbm4_usd_gb=p["hbm4_usd_gb"] * 2, hbm3e_usd_gb=p["hbm3e_usd_gb"] * 2)
    caro = {g.nome: g.preco_usd for g in c003.gpus(C, p2, ref)}
    assert all(caro[k] > base[k] for k in base)
