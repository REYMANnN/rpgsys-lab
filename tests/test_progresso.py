from jobs.progresso import calcular


def test_placar_sem_status_sem_evidencia():
    _, problemas, _ = calcular()
    assert problemas == []
