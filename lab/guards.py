"""Guardas permanentes (LICOES.md): rodam antes de todo veredito."""
from __future__ import annotations

from pathlib import Path

PJ_POR_BIT_PISO = 0.3      # piso físico conservador para ler 1 bit de DRAM (pJ), ESTIMADO
LIMITE_BOM_DEMAIS = 20.0   # vantagem acima disso exige revisão manual


class GuardaFalhou(RuntimeError):
    pass


def salvar_resultado(caminho: Path, texto: str) -> None:
    """L5: resultado é imutável."""
    if caminho.exists():
        raise GuardaFalhou(f"{caminho} já existe; use novo sufixo de revisão (L5)")
    caminho.write_text(texto, encoding="utf-8")


def checar_vantagem(nome: str, A: float) -> list[str]:
    """L6: bom demais é bug até prova em contrário."""
    if A != A or A <= 0:
        return [f"{nome}: vantagem inválida {A}"]
    if A > LIMITE_BOM_DEMAIS:
        return [f"{nome}: vantagem {A:.1f}x acima de {LIMITE_BOM_DEMAIS}x, revisão manual obrigatória"]
    return []


def checar_energia_fisica(nome: str, potencia_total_w: float, passo_s: float, bits_lidos_por_passo: float) -> list[str]:
    """L6: energia por bit lido não pode ficar abaixo do piso físico de DRAM."""
    if bits_lidos_por_passo <= 0:
        return []
    pj_bit = potencia_total_w * passo_s / bits_lidos_por_passo * 1e12
    if pj_bit < PJ_POR_BIT_PISO:
        return [f"{nome}: {pj_bit:.3f} pJ/bit abaixo do piso físico {PJ_POR_BIT_PISO} pJ/bit"]
    return []
