"""FIS001: aplica o Lab 2 v0 aos finalistas da C001b-r1 (conforme prereg)."""
from __future__ import annotations

import json
import random
import sys
from pathlib import Path

from lab.fisico import orcamento_logica_w, placas_por_rack_ar, temperatura_base
from lab.guards import salvar_resultado
from lab.manifest import run_job
from lab.params import load, prereg_travado

ROOT = Path(__file__).resolve().parent.parent
MAPA = {"camadas": "camadas_dram", "esp_lig_um": "espessura_ligacao_um", "k_lig": "k_ligacao_w_mk",
        "esp_die_um": "espessura_die_um", "r_tim": "r_tim_m2k_w", "h_liq": "h_liquido_w_m2k",
        "h_ar": "h_ar_w_m2k", "area_mm2": "area_pilha_mm2", "t_ref": "t_refrigerante_c"}


def termo(P, rng=None):
    T = P["termico"]
    if rng is None:
        return {k: T[v]["nominal"] for k, v in MAPA.items()}
    return {k: (T[v]["nominal"] if T[v]["low"] == T[v]["high"] else rng.triangular(T[v]["low"], T[v]["high"], T[v]["nominal"]))
            for k, v in MAPA.items()}


def potencias_pilha(P, design, rng=None):
    pr, mem = P["projeto"], P["memoria"]
    def g(x):
        return x["nominal"] if rng is None else rng.triangular(x["low"], x["high"], x["nominal"])
    p_dram = g(mem["w_por_pilha_hbm"])
    p_log = 0.0
    if design["ama"]:
        p_log = g(pr["ama_w_logica_por_pilha"]) + g(pr["ama_tf_fp8_por_pilha"]) * 1e12 * 2 * g(pr["pj_por_flop_fp4"]) * 1e-12
    return p_dram, p_log


def rodar(inputs, seed):
    P = inputs["params"]
    t_max = P["termico"]["t_limite_dram_c"]["nominal"] - 5
    out = {}
    # plausibilidade: pilha padrão 40 W, líquido, sem lógica
    t = termo(P)
    plaus = {c: temperatura_base(t, 40.0, 0.0, t["h_liq"], c) for c in ("conservador", "distribuido")}
    out["plausibilidade_pilha_padrao_40W_liquido_C"] = plaus
    out["plausibilidade_ok"] = all(50 <= v <= 85 for v in plaus.values())
    rng = random.Random(seed)
    for d in inputs["designs"]:
        p_dram, p_log = potencias_pilha(P, d)
        r = {"p_dram_w": p_dram, "p_logica_w": p_log}
        for resf in ("liquido", "ar"):
            h = t["h_liq"] if resf == "liquido" else t["h_ar"]
            for c in ("conservador", "distribuido"):
                r[f"T_{resf}_{c}_C"] = temperatura_base(t, p_dram, p_log, h, c)
                r[f"orcamento_logica_{resf}_{c}_W"] = orcamento_logica_w(t, p_dram, h, c, t_max)
        cons, dist = r["T_liquido_conservador_C"], r["T_liquido_distribuido_C"]
        r["veredito"] = "APROVADO" if cons <= t_max else ("ZONA_CINZA" if dist <= t_max else "REPROVADO")
        ok = {"conservador": 0, "distribuido": 0}
        N = inputs["mc_n"]
        for _ in range(N):
            tt = termo(P, rng)
            pd, pl = potencias_pilha(P, d, rng)
            for c in ok:
                ok[c] += temperatura_base(tt, pd, pl, tt["h_liq"], c) <= t_max
        r["mc_prob_ok_liquido"] = {c: v / N for c, v in ok.items()}
        lim = P["termico"]["limite_rack_ar_kw"]
        infra = P["infra_energia"]["p_infra_w_por_acel"]["nominal"]
        r["placas_por_rack_ar"] = {k: placas_por_rack_ar(d["potencia_placa_w"], infra, lim[k]) for k in ("low", "nominal", "high")}
        out[d["nome"]] = r
    return out


if __name__ == "__main__":
    assert prereg_travado("FIS001")
    mc = int(sys.argv[1]) if len(sys.argv) > 1 else 10000
    c = json.loads((ROOT / "results" / "C001b-r1_mc10000.json").read_text())["outputs"]
    designs = []
    for chave in ("nominal|sem_restricao_tpp", "nominal|com_restricao_tpp"):
        top = c[chave]["top10"][0]
        designs.append({"nome": f"{chave.split('|')[1]}:{top['design']}", "ama": "AMA" in top["design"],
                        "potencia_placa_w": top["meta"]["potencia_w"]})
    man = run_job("FIS001", lambda i, s: rodar(i, s), {"params": load("params.yaml"), "designs": designs, "mc_n": mc}, seed=20261125)
    salvar_resultado(ROOT / "results" / f"FIS001_mc{mc}.json", man.to_json())
    print(json.dumps(man.outputs, indent=1, ensure_ascii=False))
