import random
from jobs.c001 import _sobol_s1


def test_constante_e_bool_nao_tem_indice():
    r = random.Random(1)
    am = []
    for _ in range(2000):
        x = r.random()
        am.append(({"x": x, "c": 5.0, "b": True, "ruido": r.random()}, 3 * x + 0.1 * r.random()))
    s = _sobol_s1(am, 1)
    assert "c" not in s and "b" not in s
    assert s["x"] > 0.9 and s["ruido"] < 0.05
