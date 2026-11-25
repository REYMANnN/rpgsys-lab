"""LICOES.md: as guardas pegam os erros que já cometemos."""
import pytest

from lab.guards import GuardaFalhou, checar_energia_fisica, checar_vantagem, salvar_resultado


def test_L5_resultado_imutavel(tmp_path):
    f = tmp_path / "r.json"
    salvar_resultado(f, "{}")
    with pytest.raises(GuardaFalhou):
        salvar_resultado(f, "{}")


def test_L6_bom_demais():
    assert checar_vantagem("x", 25.0)
    assert not checar_vantagem("x", 5.0)


def test_L6_energia_abaixo_do_piso_fisico():
    # 1 W por 1 s lendo 1e14 bits = 0,01 pJ/bit: impossível
    assert checar_energia_fisica("x", 1.0, 1.0, 1e14)
    assert not checar_energia_fisica("x", 1000.0, 0.05, 1e12)
