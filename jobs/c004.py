"""Campanha C004 (prereg/C004.yaml): treino, destilação, conversa curta; placa única vs par."""
from __future__ import annotations

import itertools
import json
import math
import sys
from pathlib import Path

from jobs import c003
from jobs.c001 import _arred, workloads
from lab.guards import salvar_resultado
from lab.manifest import run_job
from lab.params import load, prereg_travado
from lab.system_model import avaliar
from lab.treino import avaliar_treino

ROOT = Path(__file__).resolve().parent.parent
PESOS = {"W1": 0.20, "W2": 0.20, "WK": 0.30, "T1": 0.15, "T2": 0.15}


def espaco():
    yield from c003.espaco()
    for a, s, link in itertools.product([800, 1200], [0, 256], (0.4, 0.8)):
        for t in ("HBM3E", "HBM4"):
            for u in (4, 6, 8, 12):
                for lp in (0, 8):
                    yield (a, s, t, u, False, 0, link, lp, False)
                    yield (a, s, t, u, True, 50, link, lp, True)


def cargas_inferencia(Wy, ov):
    w = workloads(Wy, "nominal", ov)
    wk = dict(w["W1"], D=1024, ctx=8596.0, L_out=182.1, Z=2.91)
    return {"W1": w["W1"], "W2": w["W2"], "WK": wk}


def refs_gpu(gs, wls, p):
    R = {}
    for k, wl in wls.items():
        rs = {g.nome: avaliar(g, wl, p) for g in gs}
        ok = {n: r for n, r in rs.items() if r.ok}
        R[k] = (min(ok.items(), key=lambda kv: kv[1].custo_usd_mtok), max(ok.items(), key=lambda kv: kv[1].tok_por_j))
    for t in ("T1", "T2"):
        rs = {g.nome: avaliar_treino(g, t, p) for g in gs}
        R[t] = (min(rs.items(), key=lambda kv: kv[1]["custo_usd_mtok"]), max(rs.items(), key=lambda kv: kv[1]["tok_por_j"]))
    return R


def notas(P, p, args, wls, R, fe):
    d, meta, fis = c003.montar(P["memorias"], p, args, fe)
    if not fis["ok"]:
        return None
    out = {"design": d.nome, "args": list(args), "meta": meta, "T_C": fis["T_liq_C"]}
    for k, wl in wls.items():
        r = avaliar(d, wl, p)
        if not r.ok:
            out[k] = None
            continue
        (gc, rc), (ge, re_) = R[k]
        out[k] = {"custo": rc.custo_usd_mtok / r.custo_usd_mtok, "energia": r.tok_por_j / re_.tok_por_j, "gpu": gc}
    for t in ("T1", "T2"):
        r = avaliar_treino(d, t, p, fe)
        (gc, rc), (ge, re_) = R[t]
        out[t] = {"custo": rc["custo_usd_mtok"] / r["custo_usd_mtok"], "energia": r["tok_por_j"] / re_["tok_por_j"], "gpu": gc, "n": r["n"]}
    return out


def nota(o, k):
    x = o.get(k)
    return 0.0 if not x else min(x["custo"], x["energia"])


def mistura(fn):
    if any(fn(k) <= 0 for k in PESOS):
        return 0.0
    return math.exp(sum(w * math.log(fn(k)) for k, w in PESOS.items()))


def cenario(P, Wy, C, ov, p, fe):
    wls = cargas_inferencia(Wy, ov)
    R = refs_gpu(c003.gpus(C, p, c003.nominais_mem(P)), wls, p)
    ds = [o for a in espaco() if (o := notas(P, p, a, wls, R, fe)) is not None]
    res = {"n_designs": len(ds), "gpu_referencia": {k: [R[k][0][0], R[k][1][0]] for k in R}}
    res["melhor_por_carga"] = {k: max(ds, key=lambda o: nota(o, k)) for k in PESOS}
    unica = max(ds, key=lambda o: mistura(lambda k: nota(o, k)))
    res["melhor_unica"] = {"design": unica, "nota_mistura": mistura(lambda k: nota(unica, k))}
    # melhor par: candidatos = top 40 de inferência (W1,W2,WK) e top 40 de treino (T1,T2)
    inf = sorted(ds, key=lambda o: mistura(lambda k: nota(o, k) if k in ("W1", "W2", "WK") else 1.0), reverse=True)[:40]
    tre = sorted(ds, key=lambda o: min(nota(o, "T1"), nota(o, "T2")), reverse=True)[:40]
    melhor_par = None
    for a in inf:
        for b in tre:
            m = mistura(lambda k: max(nota(a, k), nota(b, k)))
            if melhor_par is None or m > melhor_par[0]:
                melhor_par = (m, a, b)
    res["melhor_par"] = {"nota_mistura": melhor_par[0], "inferencia": melhor_par[1], "calculo": melhor_par[2]}
    res["ganho_par_sobre_unica"] = melhor_par[0] / res["melhor_unica"]["nota_mistura"] if res["melhor_unica"]["nota_mistura"] else None
    res["produto_C003_aqui"] = notas(P, p, (400, 2048, "HBM4", 12, True, 100, 0.4, 8, True), wls, R, fe)
    return res


def campanha(inputs, seed):
    P, Wy, C, ov = inputs["params"], inputs["workloads"], inputs["competitors"], inputs["overlay"]
    pn = c003.params(P)
    return {"nominal": cenario(P, Wy, C, ov, pn, 1.0), "software_imaturo": cenario(P, Wy, C, ov, pn, 0.6)}


if __name__ == "__main__":
    assert prereg_travado("C004")
    inputs = {"params": load("params.yaml"), "workloads": load("workloads.yaml"), "competitors": load("competitors.yaml"),
              "overlay": load("workloads_med001.yaml")}
    man = run_job("C004", lambda i, s: _arred(campanha(i, s)), inputs, seed=0)
    salvar_resultado(ROOT / "results" / "C004.json", man.to_json())
    print("ok")
