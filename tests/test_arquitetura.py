import copy
from lab import arquitetura as AR


def test_planta_sem_falhas():
    F, M = AR.checar(AR.carregar())
    assert F == []
    assert M["ocupacao"] <= 0.90


def test_detecta_sobreposicao_e_excesso_de_pilhas():
    A = copy.deepcopy(AR.carregar())
    A["interposer"]["posicoes"]["H1"] = [5.0, 0.5]
    F, _ = AR.checar(A)
    assert any("sobrepõe" in f for f in F)
    A = copy.deepcopy(AR.carregar())
    A["chip_calculo"]["dimensoes_mm"] = [33.0, 30.0]
    F, _ = AR.checar(A)
    assert any("retículo" in f or "janela" in f or "sai do" in f or "sobrepõe" in f for f in F)
