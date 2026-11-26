"""MED002: Z, contexto e saída de tráfego real (Mooncake toolagent) + produto C003 nessa carga."""
from __future__ import annotations

import json
import statistics as st
from pathlib import Path

from jobs import c003
from jobs.c001 import _arred, workloads
from lab.guards import salvar_resultado
from lab.manifest import run_job
from lab.params import load, prereg_travado

ROOT = Path(__file__).resolve().parent.parent


def sessoes(reqs, passo):
    por_bloco = {}
    for idx, r in enumerate(reqs):
        if len(r["hash_ids"]) >= 2:
            por_bloco.setdefault(r["hash_ids"][0], []).append(idx)
    zs, ctxs, encadeados = [], [], 0
    for j, r in enumerate(reqs):
        best = None
        for i in por_bloco.get(r["hash_ids"][0], []):
            if i >= j:
                break
            a = reqs[i]
            if a["timestamp"] >= r["timestamp"] or len(a["hash_ids"]) < 2:
                continue
            pref = a["hash_ids"][:-1]
            if r["hash_ids"][:len(pref)] != pref:
                continue
            if r["input_length"] < a["input_length"] + a["output_length"]:
                continue
            best = i
        if best is not None:
            a = reqs[best]
            encadeados += 1
            zs.append((r["timestamp"] - a["timestamp"]) / 1000 - a["output_length"] * passo)
            ctxs.append(r["input_length"])
    return zs, ctxs, encadeados


def q(x, p):
    s = sorted(x)
    return s[int(p * (len(s) - 1))]


def medir(inputs, seed):
    reqs = sorted(inputs["reqs"], key=lambda r: r["timestamp"])
    out = {"pedidos": len(reqs), "entrada_media": st.mean(r["input_length"] for r in reqs),
           "saida_media": st.mean(r["output_length"] for r in reqs)}
    for passo in (0.015, 0.030, 0.060):
        zs, ctxs, enc = sessoes(reqs, passo)
        zp = [z for z in zs if z > 0]
        out[f"passo_{int(passo*1000)}ms"] = {"encadeados": enc, "frac_encadeados": enc / len(reqs),
            "Z_mediana_s": st.median(zp), "Z_media_s": st.mean(zp), "Z_p10_s": q(zp, .1), "Z_p90_s": q(zp, .9),
            "Z_negativos": len(zs) - len(zp), "ctx_media_encadeados": st.mean(ctxs)}
    # produto C003 na carga real (Z da mediana com passo 30 ms; contexto e saída medidos)
    m = out["passo_30ms"]
    P, Wy, C, ov = inputs["params"], inputs["workloads"], inputs["competitors"], inputs["overlay"]
    p = c003.params(P)
    ref = c003.nominais_mem(P)
    base = workloads(Wy, "nominal", ov)["W1"]
    res = {}
    for nome, Z in (("Z_mediana", m["Z_mediana_s"]), ("Z_media", m["Z_media_s"]), ("Z_p90", m["Z_p90_s"])):
        wl = dict(base, Z=Z, ctx=out["entrada_media"], L_out=out["saida_media"])
        refs = {"W_kimi": c003.melhor_gpu(c003.gpus(C, p, ref), wl, p)}
        o = c003.avaliar_design(P["memorias"], p, (400, 2048, "HBM4", 12, True, 100, 0.4, 8, True), {"W_kimi": wl}, refs)
        r = o["W_kimi"] if o else None
        res[nome] = None if r is None else {"Z_s": Z, "A_custo": r["A_custo"], "A_energia": r["A_energia"],
                                            "gpu_custo": r["gpu_custo"], "gpu_energia": r["gpu_energia"], "n": r["n"]}
    out["produto_C003_em_W_kimi"] = res
    return out


if __name__ == "__main__":
    assert prereg_travado("MED002")
    reqs = [json.loads(x) for x in open(ROOT / "data" / "mooncake" / "toolagent_trace.jsonl")]
    inputs = {"reqs": reqs, "params": load("params.yaml"), "workloads": load("workloads.yaml"),
              "competitors": load("competitors.yaml"), "overlay": load("workloads_med001.yaml")}
    man = run_job("MED002", lambda i, s: _arred(medir(i, s)), inputs, seed=0)
    salvar_resultado(ROOT / "results" / "MED002.json", man.to_json())
    print(json.dumps(man.outputs, indent=1, ensure_ascii=False))
