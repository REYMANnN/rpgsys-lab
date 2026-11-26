"""Simulador funcional bit a bit da pista da AMA, vetorizado (numpy).

Mesma aritmética inteira de rtl/ama_pista.py (teste: tests/test_sw_ama.py compara com a referência do RTL).
Processa várias pistas em paralelo (uma por cabeça de atenção); o laço é sobre os tokens, em ordem, como no hardware.
"""
from __future__ import annotations

import numpy as np

from rtl.ama_pista import F, LUT, Q, tabela

_T = np.array(tabela(), dtype=np.int64)


def _e2(delta):
    ip = delta >> F
    fr = (delta >> (F - LUT)) & (2 ** LUT - 1)
    r = _T[fr] >> np.minimum(ip, 63)
    return np.where(ip > Q, 0, r)


def pistas(q, K, V, escala, desloc, vexp=None):
    """q: (H, d) int8; K, V: (T, H, d) int8; escala: (H,) int. Devolve m (H,), l (H,), o (H, d) — inteiros."""
    q = q.astype(np.int64)
    K = K.astype(np.int64)
    V = V.astype(np.int64)
    esc = np.asarray(escala, dtype=np.int64)
    H, d = q.shape
    m = np.zeros(H, np.int64)
    l = np.zeros(H, np.int64)
    o = np.zeros((H, d), np.int64)
    dots = np.einsum("hd,thd->th", q, K)            # (T, H)
    S = (dots * esc[None, :]) >> np.asarray(desloc, dtype=np.int64)   # desloc: escalar ou um por pista
    for t in range(K.shape[0]):
        s = S[t]
        ve = 0 if vexp is None else vexp[t][:, None]
        if t == 0:
            m, l, o = s.copy(), np.full(H, 1 << Q, np.int64), (V[0] << Q) << ve
            continue
        mn = np.maximum(m, s)
        a = _e2(mn - m)
        b = _e2(mn - s)
        l = ((l * a) >> Q) + b
        o = ((o * a[:, None]) >> Q) + ((b[:, None] * V[t]) << ve)
        m = mn
    return m, l, o
