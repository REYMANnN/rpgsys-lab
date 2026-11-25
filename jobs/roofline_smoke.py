"""Job de fumaça da fase 0: um roofline mínimo, determinístico.

Não é resultado de engenharia. Serve só para provar que o mesmo job,
com as mesmas entradas e a mesma semente, produz o mesmo hash de saída
no GitHub Actions e no Modal.
"""
from __future__ import annotations

import random

DEFAULT_INPUTS = {
    # Valores ilustrativos [HIPÓTESE], não usados em nenhuma conclusão.
    "peak_tflops": 1000.0,
    "mem_bw_tbs": 8.0,
    "intensities_flop_per_byte": [1, 2, 4, 8, 16, 32, 64, 128, 256, 512],
    "samples": 1000,
}


def roofline(inputs: dict, seed: int) -> dict:
    peak = inputs["peak_tflops"]
    bw = inputs["mem_bw_tbs"]
    curve = {str(i): round(min(peak, bw * i), 6) for i in inputs["intensities_flop_per_byte"]}
    ridge = round(peak / bw, 6)
    # Amostragem com semente fixa: prova que a semente controla a aleatoriedade.
    rng = random.Random(seed)
    draws = [rng.uniform(0.5, 1.5) * bw for _ in range(inputs["samples"])]
    mean_bw = round(sum(draws) / len(draws), 9)
    return {"attainable_tflops": curve, "ridge_point": ridge, "mc_mean_bw_tbs": mean_bw}
