"""TCAL001: calibra k_ligacao no ponto imec 3D e testa nos outros (prereg)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

from lab.fisico import temperatura_base
from lab.guards import salvar_resultado
from lab.manifest import run_job
from lab.params import load, prereg_travado
from jobs.fis001 import termo

ROOT = Path(__file__).resolve().parent.parent


def rodar(inputs, seed):
    P = inputs["params"]
    t = termo(P)
    t["t_ref"] = 25.0
    t["h_liq"] = 300000.0
    alvo = 141.7

    def T(k):
        tt = dict(t, k_lig=k)
        return temperatura_base(tt, 30.0, 100.0, tt["h_liq"], "conservador")
    lo, hi = 0.05, 50.0
    for _ in range(200):
        mid = (lo * hi) ** 0.5
        if T(mid) > alvo:
            lo = mid
        else:
            hi = mid
    k = (lo * hi) ** 0.5
    tk = dict(t, k_lig=k)
    t25 = temperatura_base(tk, 30.0, 0.0, tk["h_liq"], "distribuido")
    erro25 = t25 - 60.0
    ok = 0.5 <= k <= 20 and abs(erro25) <= 25
    return {"k_calibrado": k, "T_imec3D_previsto": T(k), "T_imec25D_previsto": t25, "erro_imec25D": erro25,
            "veredito": "APROVADO" if ok else "REPROVADO",
            "nota": "teste H100 de campo é só sanidade (condições não publicadas)"}


if __name__ == "__main__":
    assert prereg_travado("TCAL001")
    man = run_job("TCAL001", rodar, {"params": load("params.yaml")}, seed=0)
    salvar_resultado(ROOT / "results" / "TCAL001.json", man.to_json())
    print(json.dumps(man.outputs, indent=1, ensure_ascii=False))
