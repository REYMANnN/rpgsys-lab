"""Job de calibração CAL001: ajusta eta em 2 pontos e testa no ponto cego."""
from __future__ import annotations

import json
import math
from pathlib import Path

import yaml

from lab.decode_model import Carga, Hardware, Modelo, regime, tokens_por_s_gpu
from lab.guards import salvar_resultado
from lab.manifest import run_job
from lab.params import prereg_travado

ROOT = Path(__file__).resolve().parent.parent


def carregar():
    d = yaml.safe_load((ROOT / "calib" / "points.yaml").read_text(encoding="utf-8"))
    pre = yaml.safe_load((ROOT / "prereg" / "CAL001.yaml").read_text(encoding="utf-8"))
    return d, pre


def objetos(d, nome):
    mm = d["modelo"]
    m = Modelo(mm["camadas"], mm["parametros_totais"], mm["parametros_ativos"],
               mm["kv_dim_por_camada"], mm["heads"], mm["attn_dim_efetiva"])
    p = d["pontos"][nome]
    g = d["gpus"][p["gpu"]]
    h = Hardware(g["banda_tb_s"], g[p["precisao_moe"]], g[p["precisao_atencao"]])
    c = Carga(p["contexto_medio"], p["batch_por_gpu"], p["ep"], p["bytes_peso"])
    return m, h, c, p["medido_tok_s_gpu"]


def calibrar(inputs: dict, seed: int) -> dict:
    d, pre = inputs["points"], inputs["prereg"]
    etas = {}
    for nome in pre["pontos_de_calibracao"]:
        m, h, c, med = objetos(d, nome)
        etas[nome] = med / tokens_por_s_gpu(m, h, c, 1.0)
    eta = math.exp(sum(math.log(v) for v in etas.values()) / len(etas))
    linhas, aprovado = {}, True
    for nome in pre["pontos_de_calibracao"] + [pre["ponto_cego"]]:
        m, h, c, med = objetos(d, nome)
        prev = tokens_por_s_gpu(m, h, c, eta)
        erro = prev / med - 1
        aprovado &= abs(erro) <= 0.20
        linhas[nome] = {"medido": med, "previsto": round(prev, 1), "erro": round(erro, 4),
                        "regime": regime(m, h, c), "cego": nome == pre["ponto_cego"],
                        "eta_implicito": round(med / tokens_por_s_gpu(m, h, c, 1.0), 4)}
    return {"eta": round(eta, 4), "pontos": linhas,
            "veredito": "APROVADO" if aprovado else "REPROVADO"}


if __name__ == "__main__":
    assert prereg_travado("CAL001"), "pré-registro CAL001 alterado ou ausente"
    d, pre = carregar()
    man = run_job("CAL001", calibrar, {"points": d, "prereg": pre}, seed=0)
    (ROOT / "results").mkdir(exist_ok=True)
    import sys as _s
    rev = _s.argv[1] if len(_s.argv) > 1 else ""
    salvar_resultado(ROOT / "results" / f"CAL001{rev}.json", man.to_json())
    print(json.dumps(man.outputs, indent=2, ensure_ascii=False))
