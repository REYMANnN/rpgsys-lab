"""Modelo de treino e destilação (C004). Mesmo modelo para GPUs e para as nossas placas (simetria)."""
from __future__ import annotations

from lab.system_model import Disp

MFU = 0.427          # calibrado: Llama 3.1 405B FP8 em 576 H100 (NVIDIA NGC)
LINK_REF = 0.9       # TB/s, rede de referência da calibração (NVLink H100)
TAREFAS = {
    "T1": dict(flops=6 * 22e9, mem=235e9 * 16 * 1.2, a2a=3 * 6.16e6, desc="pré-treino Qwen3-235B-A22B FP8"),
    "T2": dict(flops=2 * 22e9 + 6 * 8e9, mem=(235e9 + 8e9 * 16) * 1.2, a2a=6.16e6, desc="destilação 235B -> 8B"),
}


def avaliar_treino(d: Disp, tarefa: str, p: dict, fator_mfu: float = 1.0) -> dict:
    T = TAREFAS[tarefa]
    n_min = max(1, int(-(-T["mem"] // (d.mem_gb * 1e9 * 0.9))))
    pico = d.tf_moe / 2 * 1e12          # FP8 = metade do FP4 (as duas pontas)
    melhor = None
    for n in range(n_min, 4 * n_min + 1):
        t_calc = T["flops"] / (n * pico * MFU * fator_mfu)
        link = d.link_tb_s or LINK_REF
        pen = max(0.0, T["a2a"] / (n * link * 1e12) - T["a2a"] / (n * LINK_REF * 1e12))
        t_tok = t_calc + 0.5 * pen
        tok_s = 1.0 / t_tok
        p_slot = d.potencia_w + (0.0 if d.inclui_infra else p.get("p_infra_w", 0.0))
        p_media = n * p_slot * 0.9
        extra = 0.0 if d.inclui_infra else (p["c_host"] / 8 + p["c_net"] + p["c_rack"] / 8 + d.potencia_w * p["c_pdu"])
        c_cool = p["c_cool"] + (p.get("premio_liq", 0.0) if d.liquido else 0.0)
        capex = n * (d.preco_usd + extra + p_slot * c_cool)
        opex = p_media / 1000 * p["H"] * p["p_kwh"] * p["pue"]
        custo = (capex + opex) / (tok_s * p["H"] * 3600) * 1e6
        r = dict(n=n, custo_usd_mtok=custo, tok_por_j=tok_s / (p_media * p["pue"]), tok_s=tok_s)
        if melhor is None or custo < melhor["custo_usd_mtok"]:
            melhor = r
    return melhor
