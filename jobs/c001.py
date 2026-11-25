"""Campanha C001 — juiz automático conforme prereg/C001.yaml (travado)."""
from __future__ import annotations

import json
import math
import random
import sys
from dataclasses import replace
from pathlib import Path

from lab.designs import espaco, placa
from lab.guards import checar_energia_fisica, checar_vantagem, salvar_resultado
from lab.manifest import run_job
from lab.params import load, prereg_travado
from lab.system_model import Disp, avaliar

ROOT = Path(__file__).resolve().parent.parent

FAIXAS = {  # chave do dicionário p -> caminho no params.yaml (para Monte Carlo)
    "hbm3e_usd_gb": ("memoria", "hbm3e_usd_gb"), "hbm4_usd_gb": ("memoria", "hbm4_usd_gb"),
    "lpddr5x_usd_gb": ("memoria_commodity", "lpddr5x_usd_gb"), "gddr7_usd_gb": ("memoria_commodity", "gddr7_usd_gb"),
    "premium": ("memoria", "hbm_premium_custom_base_die"), "w_pilha": ("memoria", "w_por_pilha_hbm"),
    "p_mm2": ("silicio", "p_mm2_3nm_usd"), "p_pkg": ("silicio", "p_pkg_por_pilha_usd"), "yield": ("silicio", "yield_modulo"),
    "p_pcb": ("placa_e_sistema", "p_pcb_usd"), "p_vrm": ("placa_e_sistema", "p_vrm_usd_por_w_pico"),
    "c_host": ("placa_e_sistema", "c_host_usd"), "c_net": ("placa_e_sistema", "c_net_usd_por_acel"),
    "c_rack": ("placa_e_sistema", "c_rack_usd"), "c_pdu": ("placa_e_sistema", "c_pdu_usd_por_w"),
    "c_cool": ("placa_e_sistema", "c_cool_capex_usd_por_w"), "p_kwh": ("operacao", "p_kwh_usd"), "pue": ("operacao", "pue"),
    "nre": ("empresa", "nre_usd"), "volume": ("empresa", "volume_placas"), "software": ("empresa", "software_usd"),
    "tf_mm2": ("projeto", "tf_fp4_por_mm2"), "pj_flop": ("projeto", "pj_por_flop_fp4"), "sram_mb_mm2": ("projeto", "sram_mb_por_mm2"),
    "sram_w_mb": ("projeto", "sram_w_por_mb"), "ama_k": ("projeto", "ama_k_banda_interna"), "ama_tf": ("projeto", "ama_tf_fp8_por_pilha"),
    "ama_w": ("projeto", "ama_w_logica_por_pilha"), "p_infra_w": ("infra_energia", "p_infra_w_por_acel"), "atividade": ("projeto", "atividade_media"), "eta": ("projeto", "eta_sistema"),
}


def params_nominais(P):
    p = {k: P[a][b]["nominal"] for k, (a, b) in FAIXAS.items()}
    p.update(margem=0.40, H=26280.0)
    return p


def adverso(p):
    q = dict(p)
    q.update(hbm3e_usd_gb=25.0, hbm4_usd_gb=70.0, lpddr5x_usd_gb=21.0, gddr7_usd_gb=25.0,
             premium=0.60, nre=200e6, volume=15000, p_mm2=0.50, w_pilha=50.0)
    return q


def sorteio(P, rng):
    p = {}
    for k, (a, b) in FAIXAS.items():
        x = P[a][b]
        p[k] = rng.triangular(x["low"], x["high"], x["nominal"])
    p.update(margem=0.40, H=26280.0)
    return p


def workloads(Wy, cenario, overlay=None):
    out = {}
    for k in ("W1", "W2", "W3"):
        w = Wy["workloads"][k]
        ctx = sum(int(c) * f for c, f in w["ctx_dist"].items())
        Z = w["z_think_s"]["adverso"] if cenario == "adverso" else w["z_think_s"]["nominal"]
        L = w["l_out_tokens"]["nominal"]
        if overlay:
            L = overlay[k]["l_out_tokens"]["nominal"]
            if cenario != "adverso":
                Z = overlay[k]["z_think_s"]["nominal"]
        out[k] = dict(D=w["demanda_agentes"]["nominal"], ctx=ctx, Z=Z, L_out=L,
                      slo=w["slo_tbt_p95_s"]["nominal"])
    return out


def gpus(C):
    out = []
    for nome, g in C["modelo_sistema"].items():
        out.append(Disp(nome, g["mem_gb"], g["banda_tb_s"], g["banda_tb_s"], g["fp4"], g["fp8"],
                        g["potencia_slot_w"], g["preco_usd"], g["inclui_infra"], g["bytes_peso"]))
    return out


def melhor_gpu(gs, wl, p):
    rs = {g.nome: avaliar(g, wl, p) for g in gs}
    ok = {k: r for k, r in rs.items() if r.ok}
    custo = min(ok.items(), key=lambda kv: kv[1].custo_usd_mtok)
    energia = max(ok.items(), key=lambda kv: kv[1].tok_por_j)
    return custo, energia, rs


def avaliar_design(P_mem, p, args, wls, refs, restricao_tpp):
    d, meta = placa(p, P_mem, *args)
    if meta["area_mm2"] > 1600:
        return None
    if restricao_tpp and meta["tpp"] >= 4800:
        return None
    out = {"design": d.nome, "meta": meta}
    for w, wl in wls.items():
        r = avaliar(d, wl, p)
        if not r.ok:
            out[w] = None
            continue
        (gc, rc), (ge, re_), _ = refs[w]
        out[w] = dict(A_custo=rc.custo_usd_mtok / r.custo_usd_mtok, A_energia=r.tok_por_j / re_.tok_por_j,
                      n=r.n, custo_usd_mtok=r.custo_usd_mtok, tok_por_j=r.tok_por_j,
                      gpu_custo=gc, gpu_energia=ge, passo_s=r.passo_s,
                      bits_por_passo=r.extra.get("bits_por_passo", 0.0), potencia_media_w=r.extra.get("potencia_media_w", 0.0))
    return out


def nota(o, ws=("W1", "W2")):
    vals = []
    for w in ws:
        if not o.get(w):
            return 0.0
        vals += [o[w]["A_custo"], o[w]["A_energia"]]
    return min(vals)


def campanha(inputs, seed):
    P, Wy, C = inputs["params"], inputs["workloads"], inputs["competitors"]
    P_mem = P["memorias"]
    gs = gpus(C)
    res = {}
    for cen in ("nominal", "adverso"):
        p = params_nominais(P) if cen == "nominal" else adverso(params_nominais(P))
        wls = workloads(Wy, cen, inputs.get("overlay"))
        refs = {w: melhor_gpu(gs, wl, p) for w, wl in wls.items()}
        gpu_tab = {w: {k: (round(r.custo_usd_mtok, 3), round(r.tok_por_j, 3), r.n) if r.ok else None
                       for k, r in refs[w][2].items()} for w in wls}
        for restr in (False, True):
            ds = [avaliar_design(P_mem, p, a, wls, refs, restr) for a in espaco()]
            ds = [x for x in ds if x]
            ds.sort(key=nota, reverse=True)
            res[f"{cen}|{'com' if restr else 'sem'}_restricao_tpp"] = {"gpus": gpu_tab, "n_designs": len(ds), "top10": ds[:10]}
    # Monte Carlo no melhor design nominal sem restrição (critério A usa W1)
    P_mem = P["memorias"]
    top = res["nominal|sem_restricao_tpp"]["top10"][0]
    from lab.designs import espaco as _e  # noqa
    rng = random.Random(seed)
    alvo = top["design"]
    args = next(a for a in espaco() if placa(params_nominais(P), P_mem, *a)[0].nome == alvo)
    passa, n_ok = 0, 0
    N = inputs["mc_n"]
    amostras = []
    for _ in range(N):
        p = sorteio(P, rng)
        wls = {"W1": workloads(Wy, "nominal", inputs.get("overlay"))["W1"]}
        z_lo, z_hi, z_mode = inputs.get("z_mc", (0.5, 30.0, 3.0))
        p["Z"] = wls["W1"]["Z"] = rng.triangular(z_lo, z_hi, z_mode)
        refs = {"W1": melhor_gpu(gs, wls["W1"], p)}
        o = avaliar_design(P_mem, p, args, wls, refs, False)
        if o and o.get("W1"):
            n_ok += 1
            amostras.append((p, o["W1"]["A_custo"], o["W1"]["A_energia"]))
            if o["W1"]["A_custo"] >= 3.0 and o["W1"]["A_energia"] >= 3.0:
                passa += 1
    res["monte_carlo"] = {"design": alvo, "sorteios": N, "validos": n_ok, "frac_passa_3x": passa / N,
                          "A_custo_p10_p50_p90": _quantis([a for _, a, _ in amostras]),
                          "A_energia_p10_p50_p90": _quantis([e for _, _, e in amostras]),
                          "sobol_S1_A_custo": _sobol_s1(amostras, 1), "sobol_S1_A_energia": _sobol_s1(amostras, 2)}
    # Controles
    nom = res["nominal|sem_restricao_tpp"]
    t1 = nom["top10"][0]
    res["controles"] = {}
    p = params_nominais(P)
    wls = workloads(Wy, "nominal", inputs.get("overlay"))
    g = gs[0]
    r = avaliar(g, wls["W1"], p)
    res["controles"]["positivo_gpu_vs_ela_mesma"] = round(r.custo_usd_mtok / avaliar(g, wls["W1"], p).custo_usd_mtok, 6)
    if "AMA" in t1["design"]:
        a2 = (args[0], args[1], args[2], args[3], False)
        refs = {w: melhor_gpu(gs, wl, p) for w, wl in wls.items()}
        burra = avaliar_design(P_mem, p, a2, wls, refs, False)
        res["controles"]["negativo_placa_burra_nota"] = round(nota(burra), 3) if burra else 0.0
    # Veredito
    adv = res["adverso|sem_restricao_tpp"]["top10"]
    nn = nota(t1)
    na = nota(adv[0]) if adv else 0
    mc = res["monte_carlo"]["frac_passa_3x"]
    if nn >= 3.0 and na >= 2.0 and mc >= 0.80:
        v = "A_APROVADO"
    elif nn >= 3.0:
        v = "B_ZONA_CINZA"
    else:
        v = "C_REPROVADO"
    guardas = []
    for w in ("W1", "W2"):
        o = t1.get(w) or {}
        if o:
            guardas += checar_vantagem(f"{w}.A_custo", o["A_custo"]) + checar_vantagem(f"{w}.A_energia", o["A_energia"])
            guardas += checar_energia_fisica(w, o["potencia_media_w"], o["passo_s"], o["bits_por_passo"])
    if guardas:
        v = "INVALIDO_GUARDA"
    res["guardas"] = guardas
    res["veredito"] = {"classe": v, "nota_nominal_min_W1W2": round(nn, 3), "nota_adversa_min_W1W2": round(na, 3), "mc_frac": mc}
    return res


def _quantis(v):
    if not v:
        return None
    v = sorted(v)
    return [v[int(q * (len(v) - 1))] for q in (0.1, 0.5, 0.9)]


def _sobol_s1(amostras, idx, bins=20, top=10):
    """Índice de Sobol de 1ª ordem estimado por razão de correlação (binning)."""
    if len(amostras) < 200:
        return None
    ys = [a[idx] for a in amostras]
    m = sum(ys) / len(ys)
    var = sum((y - m) ** 2 for y in ys) / len(ys)
    if var == 0:
        return None
    out = {}
    for k in amostras[0][0]:
        if k in ("margem", "H"):
            continue
        pares = sorted((a[0][k], a[idx]) for a in amostras)
        tam = len(pares) // bins
        vb = 0.0
        for b in range(bins):
            g = [y for _, y in pares[b * tam:(b + 1) * tam]]
            if g:
                mb = sum(g) / len(g)
                vb += len(g) * (mb - m) ** 2
        out[k] = vb / len(ys) / var
    return dict(sorted(out.items(), key=lambda kv: -kv[1])[:top])


def _arred(x):
    if isinstance(x, float):
        return round(x, 4)
    if isinstance(x, dict):
        return {k: _arred(v) for k, v in x.items()}
    if isinstance(x, list):
        return [_arred(v) for v in x]
    return x


if __name__ == "__main__":
    mc_n = int(sys.argv[1]) if len(sys.argv) > 1 else 10000
    camp = sys.argv[2] if len(sys.argv) > 2 else "C001"
    assert prereg_travado("C001") and prereg_travado(camp), "pré-registro alterado"
    inputs = {"params": load("params.yaml"), "workloads": load("workloads.yaml"),
              "competitors": load("competitors.yaml"), "mc_n": mc_n}
    if camp == "C001b":
        inputs["overlay"] = load("workloads_med001.yaml")
        inputs["z_mc"] = (0.6896, 16.8, 1.9883)
    man = run_job(camp, lambda i, s: _arred(campanha(i, s)), inputs, seed=20261125)
    (ROOT / "results").mkdir(exist_ok=True)
    rev = sys.argv[3] if len(sys.argv) > 3 else ""
    salvar_resultado(ROOT / "results" / f"{camp}{rev}_mc{mc_n}.json", man.to_json())
    print(json.dumps(man.outputs["veredito"], indent=2))
