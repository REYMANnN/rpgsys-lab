"""Fase 1: a base fixa respeita as regras e o pré-registro está travado."""
from lab.params import load, prereg_travado, problemas


def test_params_sem_erros_bloqueantes():
    for nome in ("params.yaml", "workloads.yaml", "competitors.yaml"):
        erros, _ = problemas(load(nome))
        assert erros == [], f"{nome}: {erros}"


def test_correcoes_de_vies_presentes():
    p = load("params.yaml")
    assert p["memoria"]["w_por_pilha_hbm"]["low"] <= 30 < p["memoria"]["w_por_pilha_hbm"]["nominal"]
    assert p["silicio"]["flop_por_mac"]["nominal"] == 2
    assert p["placa_e_sistema"]["host_amortizado_por_placa"]["nominal"] is True
    assert p["empresa"]["software_usd"]["nominal"] > 0


def test_distribuicoes_de_contexto_somam_1():
    w = load("workloads.yaml")["workloads"]
    for k, wl in w.items():
        assert abs(sum(wl["ctx_dist"].values()) - 1.0) < 1e-9, k


def test_controle_negativo_validador_pega_hipotese_critica_sem_faixa():
    falso = {"x": {"nominal": 1, "rotulo": "HIPÓTESE", "critico": True}}
    erros, _ = problemas(falso)
    assert erros


def test_controle_negativo_validador_pega_faixa_invertida():
    falso = {"x": {"nominal": 5, "low": 6, "high": 7, "rotulo": "ESTIMADO"}}
    erros, _ = problemas(falso)
    assert erros


def test_prereg_C001_travado():
    assert prereg_travado("C001")


def test_controle_negativo_validador_pega_numero_lido_como_texto():
    falso = {"x": {"nominal": "18.6e6", "low": 1, "high": 2, "rotulo": "ESTIMADO"}}
    erros, _ = problemas(falso)
    assert erros
