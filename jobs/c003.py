"""Campanha C003 (prereg/C003.yaml): memória em camadas, microcanais, repasse simétrico de memória."""
from __future__ import annotations

import itertools
import json
import random
import sys
from dataclasses import replace
from pathlib import Path

from jobs import c002
from jobs.c001 import _arred, _quantis, _sobol_s1, nota, workloads
from lab.designs import placa
from lab.guards import checar_energia_fisica, checar_vantagem, salvar_resultado
from lab.manifest import run_job
from lab.params import load, prereg_travado
from lab.system_model import Disp, avaliar

ROOT = Path(__file__).resolve().parent.parent
TMAX = 90.0
EXTRA = {"repasse": "repasse_memoria_gpu", "h_mc": "h_microcanal_w_m2k", "usd_mc": "usd_microcanal_por_placa",
         "y_mc": "yield_microcanal", "esp_int": "espessura_interposer_um"}


def params(P, rng=None):
    c002.LATERAL = True
    p = c002.params(P, rng)
    for k, n in EXTRA.items():
        x = P["c003"][n]
        p[k] = x["nominal"] if rng is None or x["low"] == x["high"] else rng.triangular(x["low"], x["high"], x["nominal"])
    return p


def nominais_mem(P):
    return {"hbm3e_usd_gb": P["memoria"]["hbm3e_usd_gb"]["nominal"], "hbm4_usd_gb": P["memoria"]["hbm4_usd_gb"]["nominal"]}


def gpus(C, p, ref):
    out = []
    for g in c002.gpus(C):
        chave = C["memoria_gpu"][g.nome]
        delta = g.mem_gb * (p[chave] - ref[chave]) * p["repasse"]
        out.append(replace(g, preco_usd=g.preco_usd + delta))
    return out


def temperatura(termo, p_dram, p_log, h_top, microcanal, p):
    """Base da pilha: caminho de cima (placa fria) em paralelo com o de baixo (microcanais)."""
    from lab.fisico import r_pilha
    r_top = r_pilha(termo, h_top)
    if microcanal:
        r_bot = (p["esp_int"] * 1e-6 / 130.0 + 1.0 / p["h_mc"]) / (termo["area_mm2"] * 1e-6)
        r = 1.0 / (1.0 / r_top + 1.0 / r_bot)
    else:
        r = r_top
    return termo["t_ref"] + (p_dram + p_log) * r


def espaco():
    for a, s, link in itertools.product([50, 100, 200, 400], [0, 256, 1024, 2048], (0.1, 0.4, 0.8)):
        for t in ("HBM3E", "HBM4"):
            for u in (4, 6, 8, 12):
                for lp in (0, 8, 16):
                    for mc in (False, True):
                        yield (a, s, t, u, False, 0, link, lp, mc)
                        for tf in (25, 50, 100, 150):
                            yield (a, s, t, u, True, tf, link, lp, mc)
        for t, us in (("LPDDR5X", (8, 16, 32)), ("GDDR7", (8, 16, 32))):
            for u in us:
                yield (a, s, t, u, False, 0, link, 0, False)


def montar(P_mem, p, args, fator_eta=1.0):
    a, s, t, u, ama, tf, link, lp, mc = args
    q = dict(p, ama_tf=tf) if ama else p
    d, meta = placa(q, P_mem, a, s, t, u, ama)
    p_calc = d.tf_moe * p["pj_flop"]
    dens = p_calc / a
    fis = {"dens_w_mm2": dens}
    hbm = t.startswith("HBM")
    if hbm:
        termo = p["termo"]
        p_log = (p["ama_w"] + tf * 2 * p["pj_flop"]) if ama else 0.0
        lat = 21.5 * p_calc / 400.0
        fis["T_liq_C"] = temperatura(termo, p["w_pilha"], p_log, termo["h_liq"], mc, p) + lat
        fis["T_ar_C"] = temperatura(termo, p["w_pilha"], p_log, termo["h_ar"], mc, p) + lat
        fis["lateral_C"] = lat
        fis["p_logica_pilha_w"] = p_log
    else:
        fis["T_liq_C"] = fis["T_ar_C"] = 0.0
    pot = meta["potencia_w"] + lp * 6 * 1.10
    ok = fis["T_liq_C"] <= TMAX and dens <= 1.0 and meta["area_mm2"] <= 1600
    ar = fis["T_ar_C"] <= TMAX and pot <= 1000
    fis.update(ok=ok, liquido=not ar, margem_C=(TMAX - fis["T_liq_C"]) if hbm else None)
    extra_custo = link / 0.1 * p["usd_link"] + lp * 32 * p["lpddr5x_usd_gb"] + (p["usd_mc"] if mc else 0.0)
    preco = (d.preco_usd + extra_custo / (1 - p["margem"]))
    if mc:
        preco = preco / p["y_mc"]
    cap_hbm = d.mem_gb
    d = replace(d, nome=d.nome + f"|tf{tf}|link{link}|lp{lp}|{'mc' if mc else 'topo'}", preco_usd=preco,
                potencia_w=pot, link_tb_s=link, liquido=not ar, fator_eta=fator_eta,
                mem_gb=cap_hbm + lp * 32, cap_rapida_gb=(cap_hbm if lp else None), banda_lenta_tb_s=lp * 0.136)
    meta = dict(meta, potencia_w=round(pot), preco_usd=round(preco))
    return d, meta, fis


def melhor_gpu(gs, wl, p):
    return c002.melhor_gpu(gs, wl, p)


def avaliar_design(P_mem, p, args, wls, refs, fe=1.0):
    d, meta, fis = montar(P_mem, p, args, fe)
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


def cenario(P, Wy, C, ov, p, fe, zc, ref):
    wls = workloads(Wy, zc, ov)
    gs = gpus(C, p, ref)
    refs = {w: melhor_gpu(gs, wl, p) for w, wl in wls.items()}
    ds, elim = [], 0
    for a in espaco():
        o = avaliar_design(P["memorias"], p, a, wls, refs, fe)
        if o is None:
            elim += 1
        else:
            ds.append(o)
    ds.sort(key=nota, reverse=True)
    ama = [x for x in ds if x["args"][4]]
    gt = {w: {k: (round(r.custo_usd_mtok, 3), round(r.tok_por_j, 4), r.n) if r.ok else None for k, r in refs[w][2].items()} for w in wls}
    return {"gpus": gt, "n_ok": len(ds), "eliminados_fisica": elim, "top10": ds[:10], "melhor_com_ama": ama[:3]}, wls, refs


def campanha(inputs, seed):
    P, Wy, C, ov = inputs["params"], inputs["workloads"], inputs["competitors"], inputs["overlay"]
    ref = nominais_mem(P)
    fi = P["c002"]["fator_eta_software_imaturo"]["nominal"]
    pn = params(P)
    pa = c002.adverso(pn)
    res = {}
    res["nominal"], _, _ = cenario(P, Wy, C, ov, pn, 1.0, "nominal", ref)
    res["adverso"], _, _ = cenario(P, Wy, C, ov, pa, 1.0, "adverso", ref)
    res["software_imaturo"], _, _ = cenario(P, Wy, C, ov, pn, fi, "nominal", ref)
    venc = {"geral": res["nominal"]["top10"][0], "com_ama": res["nominal"]["melhor_com_ama"][0] if res["nominal"]["melhor_com_ama"] else None}
    for nome, top in venc.items():
        if top is None:
            continue
        args = tuple(top["args"])
        for cen, pp, fe, zc in (("adverso", pa, 1.0, "adverso"), ("software_imaturo", pn, fi, "nominal")):
            wls = workloads(Wy, zc, ov)
            gs = gpus(C, pp, ref)
            refs = {w: melhor_gpu(gs, wl, pp) for w, wl in wls.items()}
            res[cen][f"vencedor_{nome}_aqui"] = avaliar_design(P["memorias"], pp, args, wls, refs, fe)
        # quanto a potência fixa da AMA precisaria ser para 10 °C de folga
        if top["args"][4]:
            p2 = dict(pn)
            lo, hi = 0.0, 40.0
            for _ in range(40):
                mid = (lo + hi) / 2
                p2["ama_w"] = mid
                _, _, f = montar(P["memorias"], p2, args)
                lo, hi = (mid, hi) if f["T_liq_C"] <= TMAX - 10 else (lo, mid)
            top["ama_w_para_10C_folga"] = lo
    rng = random.Random(seed)
    mcs = {}
    for nome, top in venc.items():
        if top is None:
            continue
        args = tuple(top["args"])
        N, passa, falha, am = inputs["mc_n"], 0, 0, []
        r2 = random.Random(rng.random())
        for _ in range(N):
            p = params(P, r2)
            fe = r2.triangular(0.6, 1.0, 1.0)
            wl = workloads(Wy, "nominal", ov)["W1"]
            wl["Z"] = r2.triangular(0.6896, 16.8, 1.9883)
            p["Z"] = wl["Z"]
            refs = {"W1": melhor_gpu(gpus(C, p, ref), wl, p)}
            o = avaliar_design(P["memorias"], p, args, {"W1": wl}, refs, fe)
            if o is None:
                falha += 1
                continue
            if o.get("W1"):
                p["fator_eta"] = fe
                p.pop("termo", None)
                am.append((p, o["W1"]["A_custo"], o["W1"]["A_energia"]))
                passa += o["W1"]["A_custo"] >= 3 and o["W1"]["A_energia"] >= 3
        mcs[nome] = {"design": top["design"], "sorteios": N, "falha_fisica": falha, "frac_passa_3x": passa / N,
                     "frac_passa_2x": sum(1 for _, a, e in am if a >= 2 and e >= 2) / N,
                     "A_custo_p10_p50_p90": _quantis([a for _, a, _ in am]), "A_energia_p10_p50_p90": _quantis([e for _, _, e in am]),
                     "sobol_S1_A_custo": _sobol_s1(am, 1), "sobol_S1_A_energia": _sobol_s1(am, 2)}
    res["monte_carlo"] = mcs
    g = []
    top = venc["geral"]
    for w in ("W1", "W2"):
        o = top[w]
        g += checar_vantagem(w, o["A_custo"]) + checar_vantagem(w, o["A_energia"]) + checar_energia_fisica(w, o["pot"], o["passo_s"], o["bits"])
    vered = {}
    for nome in venc:
        if venc[nome] is None:
            continue
        nn = nota(venc[nome])
        na = nota(res["adverso"].get(f"vencedor_{nome}_aqui") or {})
        ns = nota(res["software_imaturo"].get(f"vencedor_{nome}_aqui") or {})
        mc = mcs[nome]["frac_passa_3x"]
        v = ("INVALIDO_GUARDA" if g else "A_APROVADO" if (nn >= 3 and na >= 2 and ns >= 2 and mc >= 0.8)
             else "B_ZONA_CINZA" if nn >= 3 else "C_REPROVADO")
        vered[nome] = {"classe": v, "nominal": round(nn, 3), "adverso": round(na, 3), "imaturo": round(ns, 3), "mc_frac": mc}
    res["guardas"] = g
    res["veredito"] = vered
    return res


if __name__ == "__main__":
    assert prereg_travado("C003")
    mc = int(sys.argv[1]) if len(sys.argv) > 1 else 10000
    rev = sys.argv[2] if len(sys.argv) > 2 and sys.argv[2] != "-" else ""
    inputs = {"params": load("params.yaml"), "workloads": load("workloads.yaml"), "competitors": load("competitors.yaml"),
              "overlay": load("workloads_med001.yaml"), "mc_n": mc}
    man = run_job("C003", lambda i, s: _arred(campanha(i, s)), inputs, seed=20261126)
    salvar_resultado(ROOT / "results" / f"C003{rev}_mc{mc}.json", man.to_json())
    print(json.dumps(man.outputs["veredito"], indent=1))
