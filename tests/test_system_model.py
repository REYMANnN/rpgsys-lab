"""Controles do modelo de sistema da C001."""
from dataclasses import replace

from jobs.c001 import gpus, params_nominais, workloads
from lab.designs import placa
from lab.params import load
from lab.system_model import avaliar

P = load("params.yaml"); W = load("workloads.yaml"); C = load("competitors.yaml")
p = params_nominais(P); wl = workloads(W, "nominal")["W1"]


def test_controle_positivo_mesmo_dispositivo_mesmo_custo():
    g = gpus(C)[0]
    assert avaliar(g, wl, p).custo_usd_mtok == avaliar(g, wl, p).custo_usd_mtok


def test_controle_negativo_mais_banda_de_kv_nunca_piora():
    d, _ = placa(p, P["memorias"], 50, 0, "HBM3E", 12, False)
    a = avaliar(d, wl, p)
    b = avaliar(replace(d, banda_kv_tb_s=d.banda_kv_tb_s * 4), wl, p)
    assert b.ok and b.custo_usd_mtok <= a.custo_usd_mtok


def test_controle_negativo_preco_maior_custa_mais():
    g = gpus(C)[0]
    assert avaliar(replace(g, preco_usd=g.preco_usd * 2), wl, p).custo_usd_mtok > avaliar(g, wl, p).custo_usd_mtok


def test_simetria_mesma_eta_para_todos():
    q = dict(p); q["eta"] = p["eta"] * 2
    g = gpus(C)[0]
    assert avaliar(g, wl, q).passo_s < avaliar(g, wl, p).passo_s
