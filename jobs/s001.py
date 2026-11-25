"""S001: estresse do produto C003 (prereg/S001.yaml)."""
from __future__ import annotations

import itertools
import json
from dataclasses import replace
from pathlib import Path

import yaml

from jobs import c003
from jobs.c001 import _arred, workloads
from lab.guards import salvar_resultado
from lab.manifest import run_job
from lab.params import load, prereg_travado

ROOT = Path(__file__).resolve().parent.parent
PRODUTO = (400, 2048, "HBM4", 12, True, 100, 0.4, 8, True)
BASE = dict(Z_espera_s=None, preco_hbm_x=1.0, repasse_gpu=0.5, nosso_software_x=1.0, software_gpu_x=1.0,
            preco_gpu_x=1.0, volume_placas=None, nre_usd=None, contexto_x=1.0, potencia_pilha_w=None,
            h_microcanal=None, lateral_x=1)


def avaliar(P, Wy, C, ov, s):
    ref = c003.nominais_mem(P)
    p = c003.params(P)
    p["hbm3e_usd_gb"] *= s["preco_hbm_x"]
    p["hbm4_usd_gb"] *= s["preco_hbm_x"]
    p["repasse"] = s["repasse_gpu"]
    for k, chave in (("volume_placas", "volume"), ("nre_usd", "nre"), ("potencia_pilha_w", "w_pilha"), ("h_microcanal", "h_mc")):
        if s[k] is not None:
            p[chave] = float(s[k])  # L1: YAML lê "100e6" como texto
    wls = workloads(Wy, "nominal", ov)
    wls = {w: wl for w, wl in wls.items() if w in ("W1", "W2")}
    for wl in wls.values():
        if s["Z_espera_s"] is not None:
            wl["Z"] = s["Z_espera_s"]
        wl["ctx"] *= s["contexto_x"]
    gs = [replace(g, preco_usd=g.preco_usd * s["preco_gpu_x"], fator_eta=s["software_gpu_x"]) for g in c003.gpus(C, p, ref)]
    refs = {w: c003.melhor_gpu(gs, wl, p) for w, wl in wls.items()}
    lat_orig = None
    if s["lateral_x"] != 1:
        # escala a correção lateral: aplicada somando (x-1) vezes o termo na temperatura
        _, _, f = c003.montar(P["memorias"], p, PRODUTO)
        extra = (s["lateral_x"] - 1) * f["lateral_C"]
        if f["T_liq_C"] + extra > c003.TMAX:
            return {"ok": False, "motivo": f"térmico {f['T_liq_C'] + extra:.1f} °C", "min": 0.0}
    o = c003.avaliar_design(P["memorias"], p, PRODUTO, wls, refs, s["nosso_software_x"])
    if o is None:
        _, _, f = c003.montar(P["memorias"], p, PRODUTO)
        return {"ok": False, "motivo": f"térmico {f['T_liq_C']:.1f} °C", "min": 0.0}
    if not all(o.get(w) for w in wls):
        return {"ok": False, "motivo": "SLO/capacidade", "min": 0.0}
    vals = {f"{w}_{m}": round(o[w][f"A_{m}"], 3) for w in wls for m in ("custo", "energia")}
    return {"ok": True, "min": min(vals.values()), "T_C": round(o["fisica"]["T_liq_C"], 1), **vals}


def rodar(inputs, seed):
    P, Wy, C, ov, R = inputs["params"], inputs["workloads"], inputs["competitors"], inputs["overlay"], inputs["prereg"]
    F = R["fatores_um_por_vez"]
    out = {"base": avaliar(P, Wy, C, ov, BASE), "um_por_vez": {}, "quebra": {}}
    for k, niveis in F.items():
        linha = []
        for v in niveis:
            s = dict(BASE, **{k: v})
            if k == "repasse_gpu":
                s["preco_hbm_x"] = 2.25
            linha.append({"nivel": v, **avaliar(P, Wy, C, ov, s)})
        out["um_por_vez"][k] = linha
        q = next((x["nivel"] for x in linha if x["min"] < 2.0), None)
        out["quebra"][k] = q
    ks = list(F)
    duplas = {}
    for a, b in itertools.combinations(ks, 2):
        s = dict(BASE, **{a: F[a][2], b: F[b][2]})
        if "repasse_gpu" in (a, b):
            s["preco_hbm_x"] = max(s["preco_hbm_x"], 2.25)
        r = avaliar(P, Wy, C, ov, s)
        duplas[f"{a}+{b}"] = {"min": r["min"], "ok": r["ok"], "motivo": r.get("motivo")}
    out["duplas"] = duplas
    out["duplas_resumo"] = {"total": len(duplas), "min>=2": sum(d["min"] >= 2 for d in duplas.values()),
                            "min>=1.5": sum(d["min"] >= 1.5 for d in duplas.values()),
                            "piores5": sorted(((k, d["min"]) for k, d in duplas.items()), key=lambda x: x[1])[:5]}
    for nome, nv in (("tempestade_moderada", 1), ("tempestade_severa", 2)):
        s = dict(BASE, **{k: F[k][nv] for k in ks})
        out[nome] = {"fatores": {k: F[k][nv] for k in ks}, **avaliar(P, Wy, C, ov, s)}
    return out


if __name__ == "__main__":
    assert prereg_travado("S001")
    R = yaml.safe_load(open(ROOT / "prereg" / "S001.yaml"))
    inputs = {"params": load("params.yaml"), "workloads": load("workloads.yaml"), "competitors": load("competitors.yaml"),
              "overlay": load("workloads_med001.yaml"), "prereg": R}
    man = run_job("S001", lambda i, s: _arred(rodar(i, s)), inputs, seed=0)
    salvar_resultado(ROOT / "results" / "S001.json", man.to_json())
    o = man.outputs
    print("base", o["base"]); print("quebra", o["quebra"]); print("duplas", o["duplas_resumo"])
    print("moderada", {k: v for k, v in o["tempestade_moderada"].items() if k != "fatores"})
    print("severa", {k: v for k, v in o["tempestade_severa"].items() if k != "fatores"})
    for k, l in o["um_por_vez"].items():
        print(k, [(x["nivel"], x["min"]) for x in l])
