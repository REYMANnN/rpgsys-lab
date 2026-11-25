"""Gera os nossos designs (pilha própria) como dispositivos do modelo de sistema."""
from __future__ import annotations

import itertools

from lab.system_model import Disp


def placa(p: dict, mem: dict, area_calc: float, sram_mb: float, tipo: str, unidades: int, ama: bool) -> tuple[Disp, dict]:
    m = mem[tipo]
    area_sram = sram_mb / p["sram_mb_mm2"]
    area_total = area_calc + area_sram
    tf4 = area_calc * p["tf_mm2"]
    tf8 = tf4 / 2
    banda = unidades * m["banda_tb_s"]
    banda_kv = banda * (p["ama_k"] if ama else 1.0)
    tf_atn = tf8 + (unidades * p["ama_tf"] if ama else 0.0)
    pot = (tf4 * 1e12 * p["pj_flop"] * 1e-12 + sram_mb * p["sram_w_mb"]
           + unidades * (p["w_pilha"] if tipo.startswith("HBM") else m["w"])
           + (unidades * p["ama_w"] if ama else 0.0)) * 1.10
    premio = p["premium"] if ama else 0.0
    bom = (area_total * p["p_mm2"] + unidades * m["cap_gb"] * p[m["usd_gb_ref"]] * (1 + premio)
           + (unidades * p["p_pkg"] if tipo.startswith("HBM") else 150.0)
           + p["p_pcb"] + p["p_vrm"] * pot)
    mfg = bom / p["yield"] + (p["nre"] + p["software"]) / p["volume"]
    asp = mfg / (1 - p["margem"])
    meta = dict(area_mm2=round(area_total), tf_fp4=round(tf4), tpp=round(tf4 * 4), bom=round(bom),
                mfg=round(mfg), asp=round(asp), potencia_w=round(pot))
    nome = f"{tipo}x{unidades}|calc{area_calc}|sram{sram_mb}|{'AMA' if ama else 'plain'}"
    d = Disp(nome, unidades * m["cap_gb"], banda, banda_kv, tf4, tf_atn, pot, asp, False, sram_mb=sram_mb)
    return d, meta


def espaco():
    areas = [50, 100, 200, 400, 800, 1200]
    srams = [0, 64, 256, 1024, 2048]
    tipos = {"HBM3E": [2, 4, 6, 8, 12], "HBM4": [2, 4, 6, 8, 12], "LPDDR5X": [4, 8, 16, 32], "GDDR7": [8, 16, 32]}
    for a, s, (t, us) in itertools.product(areas, srams, tipos.items()):
        for u in us:
            for ama in ([False, True] if t.startswith("HBM") else [False]):
                yield a, s, t, u, ama
