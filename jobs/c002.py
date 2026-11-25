"""Campanha C002 (prereg/C002.yaml): C001b + física, refrigeração, rede, software imaturo."""
from __future__ import annotations

import itertools
import json
import random
import sys
from dataclasses import replace
from pathlib import Path

from jobs.c001 import FAIXAS, _arred, _quantis, _sobol_s1, nota, params_nominais, sorteio, workloads
from jobs.fis001 import MAPA as MAPA_T
from lab.designs import placa
from lab.fisico import temperatura_base
from lab.guards import checar_energia_fisica, checar_vantagem, salvar_resultado
from lab.manifest import run_job
from lab.params import load, prereg_travado
from lab.system_model import Disp, avaliar

ROOT = Path(__file__).resolve().parent.parent
EXTRA = {"premio_liq": ("c002", "premio_liquido_usd_por_w"), "usd_link": ("c002", "usd_por_100gbs_link")}
TMAX = 90.0
LATERAL = False


def params(P, rng=None):
    p = params_nominais(P) if rng is None else sorteio(P, rng)
    for k, (a, b) in EXTRA.items():
        x = P[a][b]
        p[k] = x["nominal"] if rng is None else rng.triangular(x["low"], x["high"], x["nominal"])
    p["lateral"] = LATERAL
    p["link_ref"] = P["c002"]["link_ref_tb_s"]["nominal"]
    p["bytes_a2a"] = P["c002"]["bytes_alltoall_por_token"]["nominal"]
    p["p_infra_w"] = p.get("p_infra_w", P["infra_energia"]["p_infra_w_por_acel"]["nominal"])
    T = P["termico"]
    p["termo"] = {k: (T[v]["nominal"] if rng is None or T[v]["low"] == T[v]["high"] else rng.triangular(T[v]["low"], T[v]["high"], T[v]["nominal"]))
                  for k, v in MAPA_T.items()}
    return p


def adverso(p):
    q = dict(p)
    q.update(hbm3e_usd_gb=25.0, hbm4_usd_gb=70.0, lpddr5x_usd_gb=21.0, gddr7_usd_gb=25.0,
             premium=0.60, nre=200e6, volume=15000, p_mm2=0.50, w_pilha=50.0)
    return q


def gpus(C):
    out = []
    for nome, g in C["modelo_sistema"].items():
        r = C["rede_e_refrigeracao"][nome]
        out.append(Disp(nome, g["mem_gb"], g["banda_tb_s"], g["banda_tb_s"], g["fp4"], g["fp8"], g["potencia_slot_w"],
                        g["preco_usd"], g["inclui_infra"], g["bytes_peso"], link_tb_s=r["link_tb_s"], liquido=r["liquido"]))
    return out


def espaco():
    for a, s in itertools.product([50, 100, 200, 400], [0, 256, 1024, 2048]):
        for link in (0.1, 0.4, 0.8):
            for t in ("HBM3E", "HBM4"):
                for u in (4, 6, 8, 12):
                    yield (a, s, t, u, False, 0, link)
                    for tf in (25, 50, 100, 150):
                        yield (a, s, t, u, True, tf, link)
            for t, us in (("LPDDR5X", (8, 16, 32)), ("GDDR7", (8, 16, 32))):
                for u in us:
                    yield (a, s, t, u, False, 0, link)


def montar(P_mem, p, args, fator_eta=1.0):
    a, s, t, u, ama, tf, link = args
    q = dict(p, ama_tf=tf) if ama else p
    d, meta = placa(q, P_mem, a, s, t, u, ama)
    p_calc = d.tf_moe * p["pj_flop"]
    dens = p_calc / a
    termo = p["termo"]
    fis = {"dens_w_mm2": dens}
    if t.startswith("HBM"):
        p_log = (p["ama_w"] + tf * 2 * p["pj_flop"]) if ama else 0.0
        fis["T_liq_C"] = temperatura_base(termo, p["w_pilha"], p_log, termo["h_liq"], "conservador")
        fis["T_ar_C"] = temperatura_base(termo, p["w_pilha"], p_log, termo["h_ar"], "conservador")
    else:
        fis["T_liq_C"] = fis["T_ar_C"] = 0.0
    if p.get("lateral") and t.startswith("HBM"):
        dl = 21.5 * p_calc / 400.0
        fis["T_liq_C"] += dl
        fis["T_ar_C"] += dl
        fis["lateral_C"] = dl
    ok = fis["T_liq_C"] <= TMAX and dens <= 1.0 and meta["area_mm2"] <= 1600
    ar = fis["T_ar_C"] <= TMAX and meta["potencia_w"] <= 1000
    fis.update(ok=ok, liquido=not ar, margem_C=TMAX - fis["T_liq_C"] if t.startswith("HBM") else None)
    preco_rede = link / 0.1 * p["usd_link"]
    d = replace(d, preco_usd=d.preco_usd + preco_rede, link_tb_s=link, liquido=not ar, fator_eta=fator_eta,
                nome=d.nome + f"|tf{tf}|link{link}")
    return d, meta, fis


def melhor_gpu(gs, wl, p):
    rs = {g.nome: avaliar(g, wl, p) for g in gs}
    ok = {k: r for k, r in rs.items() if r.ok}
    return min(ok.items(), key=lambda kv: kv[1].custo_usd_mtok), max(ok.items(), key=lambda kv: kv[1].tok_por_j), rs


def avaliar_design(P_mem, p, args, wls, refs, fator_eta=1.0):
    d, meta, fis = montar(P_mem, p, args, fator_eta)
    if not fis["ok"]:
        return None
    out = {"design": d.nome, "args": list(args), "meta": meta, "fisica": fis}
    for w, wl in wls.items():
        r = avaliar(d, wl, p)
        if not r.ok:
            out[w] = None
            continue
        (gc, rc), (ge, re_), _ = refs[w]
        out[w] = dict(A_custo=rc.custo_usd_mtok / r.custo_usd_mtok, A_energia=r.tok_por_j / re_.tok_por_j, n=r.n,
                      custo_usd_mtok=r.custo_usd_mtok, tok_por_j=r.tok_por_j, gpu_custo=gc, gpu_energia=ge,
                      passo_s=r.passo_s, bits=r.extra["bits_por_passo"], pot=r.extra["potencia_media_w"])
    return out


def rodar_cenario(P, Wy, C, ov, p, fator_eta, zcen):
    wls = workloads(Wy, zcen, ov)
    gs = gpus(C)
    refs = {w: melhor_gpu(gs, wl, p) for w, wl in wls.items()}
    ds, elim = [], 0
    for a in espaco():
        o = avaliar_design(P["memorias"], p, a, wls, refs, fator_eta)
        if o is None:
            elim += 1
        else:
            ds.append(o)
    ds.sort(key=nota, reverse=True)
    gt = {w: {k: (round(r.custo_usd_mtok, 3), round(r.tok_por_j, 3), r.n) if r.ok else None for k, r in refs[w][2].items()} for w in wls}
    return {"gpus": gt, "n_designs_ok": len(ds), "eliminados_fisica": elim, "top10": ds[:10]}


def campanha(inputs, seed):
    P, Wy, C, ov = inputs["params"], inputs["workloads"], inputs["competitors"], inputs["overlay"]
    fator_imaturo = P["c002"]["fator_eta_software_imaturo"]["nominal"]
    global LATERAL
    LATERAL = inputs.get("lateral", False)
    res = {}
    pn = params(P)
    res["nominal"] = rodar_cenario(P, Wy, C, ov, pn, 1.0, "nominal")
    res["adverso"] = rodar_cenario(P, Wy, C, ov, adverso(pn), 1.0, "adverso")
    res["software_imaturo"] = rodar_cenario(P, Wy, C, ov, pn, fator_imaturo, "nominal")
    top = res["nominal"]["top10"][0]
    args = tuple(top["args"])
    # mesmos designs vencedores avaliados nos cenários adversos (o vencedor nominal é o produto)
    for cen, pp, fe, zc in (("adverso", adverso(pn), 1.0, "adverso"), ("software_imaturo", pn, fator_imaturo, "nominal")):
        wls = workloads(Wy, zc, ov)
        refs = {w: melhor_gpu(gpus(C), wl, pp) for w, wl in wls.items()}
        res[cen]["vencedor_nominal_neste_cenario"] = avaliar_design(P["memorias"], pp, args, wls, refs, fe)
    rng = random.Random(seed)
    N, passa, am = inputs["mc_n"], 0, []
    falha_fis = 0
    gs = gpus(C)
    for _ in range(N):
        p = params(P, rng)
        fe = rng.triangular(0.6, 1.0, 1.0)
        wl = workloads(Wy, "nominal", ov)["W1"]
        p["Z"] = wl["Z"] = rng.triangular(0.6896, 16.8, 1.9883)
        refs = {"W1": melhor_gpu(gs, wl, p)}
        o = avaliar_design(P["memorias"], p, args, {"W1": wl}, refs, fe)
        if o is None:
            falha_fis += 1
            continue
        if o.get("W1"):
            p["fator_eta"] = fe
            am.append((p, o["W1"]["A_custo"], o["W1"]["A_energia"]))
            passa += o["W1"]["A_custo"] >= 3 and o["W1"]["A_energia"] >= 3
    for x in am:
        x[0].pop("termo", None)
    res["monte_carlo"] = {"design": top["design"], "sorteios": N, "falha_fisica": falha_fis, "frac_passa_3x": passa / N,
                          "A_custo_p10_p50_p90": _quantis([a for _, a, _ in am]),
                          "A_energia_p10_p50_p90": _quantis([e for _, _, e in am]),
                          "sobol_S1_A_custo": _sobol_s1(am, 1), "sobol_S1_A_energia": _sobol_s1(am, 2)}
    # guardas e veredito
    g = []
    for w in ("W1", "W2"):
        o = top[w]
        g += checar_vantagem(w, o["A_custo"]) + checar_vantagem(w, o["A_energia"]) + checar_energia_fisica(w, o["pot"], o["passo_s"], o["bits"])
    nn = nota(top)
    na = nota(res["adverso"]["vencedor_nominal_neste_cenario"] or {})
    ns = nota(res["software_imaturo"]["vencedor_nominal_neste_cenario"] or {})
    mc = res["monte_carlo"]["frac_passa_3x"]
    if g:
        v = "INVALIDO_GUARDA"
    elif nn >= 3 and na >= 2 and ns >= 2 and mc >= 0.8:
        v = "A_APROVADO"
    elif nn >= 3:
        v = "B_ZONA_CINZA"
    else:
        v = "C_REPROVADO"
    res["guardas"] = g
    res["veredito"] = {"classe": v, "nominal": round(nn, 3), "adverso_vencedor": round(na, 3), "software_imaturo_vencedor": round(ns, 3), "mc_frac": mc}
    return res


if __name__ == "__main__":
    camp = sys.argv[3] if len(sys.argv) > 3 else "C002"
    assert prereg_travado(camp)
    mc = int(sys.argv[1]) if len(sys.argv) > 1 else 10000
    rev = sys.argv[2] if len(sys.argv) > 2 and sys.argv[2] != "-" else ""
    inputs = {"params": load("params.yaml"), "workloads": load("workloads.yaml"), "competitors": load("competitors.yaml"),
              "overlay": load("workloads_med001.yaml"), "mc_n": mc, "lateral": camp == "C002L"}
    man = run_job(camp, lambda i, s: _arred(campanha(i, s)), inputs, seed=20261125)
    salvar_resultado(ROOT / "results" / f"{camp}{rev}_mc{mc}.json", man.to_json())
    print(json.dumps(man.outputs["veredito"], indent=1))
