"""Modelo de sistema da campanha C001: serviço agêntico, custo e energia.

Mesmo modelo para GPUs e para os nossos designs (regra de simetria):
- n dispositivos guardam uma réplica dos pesos (FP4) + o cache KV de todos os
  agentes (FP8);
- a cada passo, B agentes ativos geram 1 token; B = D * duty (ponto fixo);
- passo = max(tempo de memória, tempo de cálculo) / eta;
- custo por token = TCO no horizonte / tokens gerados;
- energia por token = potência média * PUE / tokens por segundo.
Escolhe-se, para cada lado, o n que dá o MENOR custo por token cumprindo o SLO.
"""
from __future__ import annotations

from dataclasses import dataclass, field

QWEN = dict(params=235e9, ativos=22e9, denso=8e9, camadas=94, n_q=64, n_kv=4, head=128,
            experts=128, top_k=8)


def kv_bytes_por_token(m=QWEN) -> float:
    return 2 * m["camadas"] * m["n_kv"] * m["head"] * 1.0  # K e V em FP8


def flops_atencao_por_token(ctx: float, m=QWEN) -> float:
    return 4.0 * m["n_q"] * m["head"] * ctx * m["camadas"]


@dataclass(frozen=True)
class Disp:
    """Um dispositivo (GPU ou placa nossa) visto pelo modelo de sistema."""
    nome: str
    mem_gb: float
    banda_tb_s: float          # banda para pesos
    banda_kv_tb_s: float       # banda vista pela atenção (= banda, ou k*banda na AMA)
    tf_moe: float              # pico FP4 (pesos/MLP)
    tf_atn: float              # pico FP8 da atenção
    potencia_w: float          # potência de pico do slot
    preco_usd: float           # preço ao cliente
    inclui_infra: bool
    bytes_peso: float = 0.5625
    sram_mb: float = 0.0
    link_tb_s: float | None = None   # C002: rede entre dispositivos (None = sem penalidade, como na C001)
    liquido: bool = False            # C002: precisa de refrigeração líquida
    fator_eta: float = 1.0           # C002 adverso: software imaturo
    cap_rapida_gb: float | None = None  # C003: memória em camadas — só esta parte é HBM (o resto é lenta)
    banda_lenta_tb_s: float = 0.0       # C003: banda da camada lenta (troca de KV de sessões ociosas)


@dataclass
class Resultado:
    ok: bool
    n: int = 0
    tok_s: float = 0.0
    passo_s: float = 0.0
    custo_usd_mtok: float = float("inf")
    tok_por_j: float = 0.0
    tco_usd: float = 0.0
    motivo: str = ""
    extra: dict = field(default_factory=dict)


def avaliar(d: Disp, wl: dict, p: dict, n_max_mult: int = 6) -> Resultado:
    D = wl["D"]; ctx = wl["ctx"]; Z = wl["Z"]; L = wl["L_out"]; slo = wl["slo"]
    kvt = kv_bytes_por_token()
    W = QWEN["params"] * d.bytes_peso
    need = W + D * ctx * kvt
    n_min = max(1, int(-(-need // (d.mem_gb * 1e9 * 0.9))))
    melhor = Resultado(False, motivo="SLO inatingível")
    for n in range(n_min, n_min * n_max_mult + 1):
        frac_sram = min(1.0, n * d.sram_mb * 1e6 / W) if d.sram_mb else 0.0
        B = D * 0.5
        t = 0.0
        for _ in range(60):
            tocado = 1 - (1 - QWEN["top_k"] / QWEN["experts"]) ** max(B, 1e-9)
            bw = (QWEN["denso"] + (QWEN["params"] - QWEN["denso"]) * tocado) * d.bytes_peso * (1 - frac_sram)
            t_mem = bw / (n * d.banda_tb_s * 1e12) + B * ctx * kvt / (n * d.banda_kv_tb_s * 1e12)
            t_calc = B * (2 * QWEN["ativos"] / (d.tf_moe * 1e12) + flops_atencao_por_token(ctx) / (d.tf_atn * 1e12)) / n
            t_rede = 0.0
            if d.link_tb_s and n > 1:
                remoto = B * p.get("bytes_a2a", 0.0) * (n - 1) / n
                t_rede = max(0.0, remoto / (n * d.link_tb_s * 1e12) - remoto / (n * p.get("link_ref", d.link_tb_s) * 1e12))
            t = (max(t_mem, t_calc) + t_rede) / (p["eta"] * d.fator_eta)
            duty = L * t / (L * t + Z)
            B_novo = D * duty
            if abs(B_novo - B) < 1e-6 * D:
                B = B_novo
                break
            B = 0.5 * B + 0.5 * B_novo
        if t > slo:
            continue
        if d.cap_rapida_gb is not None:
            # sessões ativas (com folga 1,5x) + pesos precisam caber na HBM; ociosas ficam na camada lenta
            if n * d.cap_rapida_gb * 1e9 * 0.9 < W + min(D, 1.5 * B) * ctx * kvt:
                continue
            # cada turno traz o KV da sessão de volta e o devolve: 2 x ctx x kvt por turno
            turnos_s = (B / t) / L
            if 2 * turnos_s * ctx * kvt > 0.5 * n * d.banda_lenta_tb_s * 1e12:
                continue
        tok_s = B / t
        p_slot = d.potencia_w + (0.0 if d.inclui_infra else p.get("p_infra_w", 0.0))
        p_media = n * p_slot * p["atividade"]
        extra_infra = 0.0 if d.inclui_infra else (p["c_host"] / 8 + p["c_net"] + p["c_rack"] / 8 + d.potencia_w * p["c_pdu"])
        c_cool = p["c_cool"] + (p.get("premio_liq", 0.0) if d.liquido else 0.0)
        capex = n * (d.preco_usd + extra_infra + p_slot * c_cool)
        opex = p_media / 1000 * p["H"] * p["p_kwh"] * p["pue"]
        tco = capex + opex
        tokens = tok_s * p["H"] * 3600
        bits = 8 * (bw + B * ctx * kvt)
        r = Resultado(True, n, tok_s, t, tco / tokens * 1e6, tok_s / (p_media * p["pue"]), tco,
                      extra={"bits_por_passo": bits, "potencia_media_w": p_media})
        if r.custo_usd_mtok < melhor.custo_usd_mtok:
            melhor = r
    return melhor
