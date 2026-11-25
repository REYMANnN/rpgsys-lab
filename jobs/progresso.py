"""Calcula o % até a meta do engenheiro a partir de gates/engenheiro.yaml."""
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent


def calcular():
    g = yaml.safe_load((ROOT / "gates" / "engenheiro.yaml").read_text(encoding="utf-8"))["gates"]
    total = sum(x["peso"] for x in g)
    feito, problemas = 0.0, []
    for x in g:
        if x["status"] > 0 and (not x["evidencia"] or not (ROOT / x["evidencia"]).exists()):
            problemas.append(f'{x["id"]}: status {x["status"]} sem evidência no repositório')
            continue
        feito += x["peso"] * x["status"]
    return round(100 * feito / total, 1), problemas, g


if __name__ == "__main__":
    pct, probs, g = calcular()
    print(f"Progresso até 'engenheiro confirma fabricável': {pct}%")
    for p in probs:
        print("  PROBLEMA:", p)
