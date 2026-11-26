import random
import numpy as np
from rtl.ama_pista import referencia, D
from sw.ama_numpy import pistas


def test_numpy_igual_ao_rtl():
    r = random.Random(7)
    for _ in range(100):
        T = r.randint(1, 80)
        H = 3
        q = np.array([[r.randint(-128, 127) for _ in range(D)] for _ in range(H)])
        K = np.array([[[r.randint(-128, 127) for _ in range(D)] for _ in range(H)] for _ in range(T)])
        V = np.array([[[r.randint(-128, 127) for _ in range(D)] for _ in range(H)] for _ in range(T)])
        esc = [r.randint(1, 60000) for _ in range(H)]
        m, l, o = pistas(q, K, V, esc, 16)
        for h in range(H):
            mr, lr, orr = referencia(list(q[h]), [list(K[t, h]) for t in range(T)], [list(V[t, h]) for t in range(T)], esc[h], 16)
            assert (int(m[h]), int(l[h]), [int(x) for x in o[h]]) == (mr, lr, orr)
