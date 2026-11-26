"""NET001: simulação de fluxo do all-to-all MoE entre as placas do produto (prereg/NET001.yaml)."""
from __future__ import annotations

import json
import random
from pathlib import Path

from jobs import c003
from jobs.c001 import _arred, workloads
from lab.guards import salvar_resultado
from lab.manifest import run_job
from lab.params import load, prereg_travado
from lab.system_model import QWEN

ROOT = Path(__file__).resolve().parent.parent
PROD = (400, 2048, "HBM4", 12, True, 100, 0.4, 8, True)
D_MODEL, TOPK, CAMADAS = 4096, 8, 94


def all_to_all(n, B, rng, topologia, banda_tb_s):
    """Bytes no enlace mais carregado para um all-to-all (ida) com B tokens espalhados nas n placas."""
    carga = [[0.0] * n for _ in range(n)]   # origem x destino
    for t in range(int(round(B))):
        o = t % n
        for _ in range(TOPK):
            dst = rng.randrange(QWEN["experts"]) % n
            if dst != o:
                carga[o][dst] += D_MODEL
    if topologia == "chave_unica":
        sai = max(sum(l) for l in carga)
        entra = max(sum(carga[o][d] for o in range(n)) for d in range(n))
        return max(sai, entra) / (banda_tb_s * 1e12)
    # anel bidirecional: caminho mais curto; soma a carga de cada enlace
    enl = {}
    for o in range(n):
        for d in range(n):
            if carga[o][d] == 0:
                continue
            passo = 1 if (d - o) % n <= n // 2 else -1
            x = o
            while x != d:
                y = (x + passo) % n
                enl[(x, y)] = enl.get((x, y), 0) + carga[o][d]
                x = y
    return max(enl.values(), default=0) / (banda_tb_s / 2 * 1e12)


def rodar(inputs, seed):
    P, Wy, C, ov = inputs["params"], inputs["workloads"], inputs["competitors"], inputs["overlay"]
    p = c003.params(P)
    ref = c003.nominais_mem(P)
    out = {}
    for w in ("W1", "W2"):
        wl = workloads(Wy, "nominal", ov)[w]
        refs = {w: c003.melhor_gpu(c003.gpus(C, p, ref), wl, p)}
        o = c003.avaliar_design(P["memorias"], p, PROD, {w: wl}, refs)[w]
        n, t = o["n"], o["passo_s"]
        B = o["custo_usd_mtok"] and (t * (o["tok_por_j"] * o["pot"] * p["pue"]))   # tok/s x t = B
        rng = random.Random(seed)
        res = {"n_placas": n, "passo_modelo_s": t, "B_tokens_por_passo": B}
        for topo in ("chave_unica", "anel"):
            ts = [all_to_all(n, B, rng, topo, 0.4) for _ in range(200)]
            banda = sum(ts) / len(ts)
            for lat_us in (1.5, 3.0, 6.0):
                rede = CAMADAS * 2 * (banda + lat_us * 1e-6)
                res[f"{topo}_lat{lat_us}"] = {"rede_por_passo_s": rede, "passo_simulado_s": t + rede,
                                              "razao_vs_modelo": (t + rede) / t}
        out[w] = res
    pior = max(v["razao_vs_modelo"] for w in out.values() for k, v in w.items() if isinstance(v, dict) and "chave_unica_lat3.0" == k)
    out["veredito"] = "VALIDADO" if pior <= 1.10 else "REFAZER_COM_PENALIDADE_SIMULADA"
    return out


if __name__ == "__main__":
    assert prereg_travado("NET001")
    inputs = {"params": load("params.yaml"), "workloads": load("workloads.yaml"), "competitors": load("competitors.yaml"),
              "overlay": load("workloads_med001.yaml")}
    man = run_job("NET001", lambda i, s: _arred(rodar(i, s)), inputs, seed=1)
    salvar_resultado(ROOT / "results" / "NET001.json", man.to_json())
    print(json.dumps(man.outputs, indent=1, ensure_ascii=False))
