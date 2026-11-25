"""Lab 2 v0: modelo térmico 1D da pilha HBM e densidade de rack (FIS001)."""
from __future__ import annotations


def r_pilha(t: dict, h: float) -> float:
    """Resistência térmica base-die -> refrigerante (K/W), condução 1D em série."""
    n = t["camadas"]
    r_area = (n * t["esp_lig_um"] * 1e-6 / t["k_lig"]
              + n * t["esp_die_um"] * 1e-6 / 130.0
              + t["r_tim"] + 1.0 / h)
    return r_area / (t["area_mm2"] * 1e-6)


def temperatura_base(t: dict, p_dram_w: float, p_logica_w: float, h: float, caso: str) -> float:
    r = r_pilha(t, h)
    if caso == "conservador":
        return t["t_ref"] + (p_dram_w + p_logica_w) * r
    return t["t_ref"] + p_logica_w * r + p_dram_w * r * 0.5


def orcamento_logica_w(t: dict, p_dram_w: float, h: float, caso: str, t_max: float) -> float:
    r = r_pilha(t, h)
    folga = t_max - t["t_ref"] - (p_dram_w * r if caso == "conservador" else p_dram_w * r * 0.5)
    return folga / r


def placas_por_rack_ar(potencia_placa_w: float, infra_w: float, limite_kw: float) -> int:
    return int(limite_kw * 1000 // (potencia_placa_w + infra_w))
