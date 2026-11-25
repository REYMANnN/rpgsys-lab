"""Controles do modelo de decode e da calibração CAL001."""
from dataclasses import replace

from jobs.calibrate import carregar, objetos
from lab.decode_model import regime, tokens_por_s_gpu
from lab.params import prereg_travado


def test_controle_positivo_gpu_contra_ela_mesma():
    d, _ = carregar()
    m, h, c, _ = objetos(d, "P2_GB200_SGLang_2025_09")
    a = tokens_por_s_gpu(m, h, c, 0.2)
    assert abs(a / tokens_por_s_gpu(m, h, c, 0.2) - 1.0) < 1e-12


def test_controle_negativo_banda_so_importa_se_limitado_por_memoria():
    d, _ = carregar()
    m, h, c, _ = objetos(d, "P3_GB300_SGLang_2026_02_longctx")
    assert regime(m, h, c) == "memoria"
    assert tokens_por_s_gpu(m, replace(h, banda_tb_s=h.banda_tb_s * 2), c, 0.2) > tokens_por_s_gpu(m, h, c, 0.2)
    m, h, c, _ = objetos(d, "P1_H100_SGLang_2025_05")
    assert regime(m, h, c) == "calculo"
    assert tokens_por_s_gpu(m, replace(h, banda_tb_s=h.banda_tb_s * 2), c, 0.2) == tokens_por_s_gpu(m, h, c, 0.2)


def test_prereg_CAL001_travado():
    assert prereg_travado("CAL001")


def test_hipotese_de_batch_nao_move_pontos_limitados_por_calculo():
    """P1 e P2 têm batch não publicado (HIPÓTESE 256). Em regime de cálculo o
    batch cancela. Medido: P1 fica em cálculo de 64 a 1024; P2 só a partir de
    ~192 por GPU (com 128 o cego cai para -17,7%; com 64, -44%). O teste trava
    a faixa em que a conclusão vale; a dependência está no README."""
    d, _ = carregar()
    for nome in ("P1_H100_SGLang_2025_05", "P2_GB200_SGLang_2025_09"):
        m, h, c, _ = objetos(d, nome)
        base = tokens_por_s_gpu(m, h, c, 0.2)
        for b in (192, 512, 1024):
            c2 = replace(c, batch_por_gpu=b)
            assert regime(m, h, c2) == "calculo"
            assert abs(tokens_por_s_gpu(m, h, c2, 0.2) / base - 1) < 1e-9
