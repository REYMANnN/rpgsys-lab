"""Modelo analítico de decode para LLMs MoE (fase 2).

Por passo de decode, numa GPU com batch B e contexto médio c:
  bytes  = pesos_por_gpu + B * c * kv_bytes_por_token
  t_mem  = bytes / banda
  t_calc = B * (F_denso / pico_moe + F_atencao(c) / pico_atencao)
  t      = max(t_mem, t_calc) / eta
  tokens/s/GPU = B / t

eta é UMA eficiência de sistema (kernels, comunicação, agendamento),
calibrada contra GPUs reais e aplicada igualmente a todo hardware.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Modelo:
    camadas: int
    parametros_totais: float
    parametros_ativos: float
    kv_dim_por_camada: int
    heads: int
    attn_dim_efetiva: int
    kv_bytes_por_elemento: float = 1.0  # FP8

    @property
    def kv_bytes_por_token(self) -> float:
        return self.camadas * self.kv_dim_por_camada * self.kv_bytes_por_elemento

    @property
    def flops_denso_por_token(self) -> float:
        return 2.0 * self.parametros_ativos

    def flops_atencao_por_token(self, ctx: float) -> float:
        return 2.0 * self.heads * ctx * self.attn_dim_efetiva * self.camadas


@dataclass(frozen=True)
class Hardware:
    banda_tb_s: float
    pico_moe_tflops: float
    pico_atencao_tflops: float


@dataclass(frozen=True)
class Carga:
    contexto_medio: float
    batch_por_gpu: float
    ep: int
    bytes_peso: float


def tempos(m: Modelo, h: Hardware, c: Carga) -> tuple[float, float]:
    pesos = m.parametros_totais * c.bytes_peso / c.ep
    kv = c.batch_por_gpu * c.contexto_medio * m.kv_bytes_por_token
    t_mem = (pesos + kv) / (h.banda_tb_s * 1e12)
    t_calc = c.batch_por_gpu * (
        m.flops_denso_por_token / (h.pico_moe_tflops * 1e12)
        + m.flops_atencao_por_token(c.contexto_medio) / (h.pico_atencao_tflops * 1e12)
    )
    return t_mem, t_calc


def tokens_por_s_gpu(m: Modelo, h: Hardware, c: Carga, eta: float) -> float:
    t_mem, t_calc = tempos(m, h, c)
    return c.batch_por_gpu * eta / max(t_mem, t_calc)


def regime(m: Modelo, h: Hardware, c: Carga) -> str:
    t_mem, t_calc = tempos(m, h, c)
    return "memoria" if t_mem >= t_calc else "calculo"
