"""G17 — um comando reproduz tudo: `python reproduzir.py` (ou `--rapido` sem as campanhas de 10 mil sorteios).

Para cada resultado vigente: roda de novo a partir do código e dos dados do repositório, num diretório
temporário, e compara o hash SHA-256 das saídas com o arquivo guardado em results/. Depois roda os testes,
a checagem da planta (G09), o RTL bit a bit (G10) e a verificação formal limitada.
Sai com código 0 só se tudo bater.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VOLATEIS = {"segundos"}   # L12: tempo de relógio não é resultado


def hash_estavel(arq):
    from lab.manifest import sha256_of
    o = json.loads(Path(arq).read_text())["outputs"]
    return sha256_of({k: v for k, v in o.items() if k not in VOLATEIS})
VIGENTES = [  # (arquivo em results/, comando)
    ("CAL001.json", ["-m", "jobs.calibrate"]),
    ("TCAL001.json", ["-m", "jobs.tcal001"]),
    ("MED001.json", ["-m", "jobs.med001"]),
    ("S001.json", ["-m", "jobs.s001"]),
    ("C003_mc10000.json", ["-m", "jobs.c003", "10000"]),
    ("MED002.json", ["-m", "jobs.med002"]),
    ("SW002A.json", ["sw/qwen_na_ama.py", "SW002", "A"]),        # precisa de torch + transformers (baixa Qwen3-0.6B)
    ("SW003FP8.json", ["sw/qwen_na_ama.py", "SW003", "FP8"]),
]
LENTOS = ("10000", "sw/qwen_na_ama.py")
HISTORICOS = ["C001_mc10000.json", "C001-r1_mc10000.json", "C001b-r1_mc10000.json", "FIS001_mc10000.json",
              "C002_mc10000.json", "C002L_mc10000.json", "C002-r1_mc10000.json", "C002L-r1_mc10000.json"]


def main(rapido=False):
    ok = True
    tmp = Path(tempfile.mkdtemp(prefix="repro_"))
    env = dict(os.environ, LAB_REPRO_DIR=str(tmp))
    for arq, cmd in VIGENTES:
        if rapido and any(x in cmd for x in LENTOS):
            print(f"[pulado --rapido] {arq}")
            continue
        r = subprocess.run([sys.executable, *cmd], cwd=ROOT, env=env, capture_output=True, text=True)
        if r.returncode != 0:
            print(f"[FALHOU] {arq}: {r.stderr[-300:]}")
            ok = False
            continue
        a = hash_estavel(ROOT / "results" / arq)
        b = hash_estavel(tmp / arq)
        print(f"[{'OK' if a == b else 'DIFERENTE'}] {arq}  {a[:12]} vs {b[:12]}")
        ok &= a == b
    print("[histórico] reproduzíveis no commit em que foram gerados (campo 'commit' do manifesto):", ", ".join(HISTORICOS))
    for nome, cmd in (("testes", ["-m", "pytest", "-q"]), ("planta G09", ["-m", "lab.arquitetura"]),
                      ("formal G10", ["formal/ama_formal.py"])):
        if rapido and nome.startswith("formal"):
            print("[pulado --rapido] formal G10 (roda no CI: job rtl_formal)")
            continue
        r = subprocess.run([sys.executable, *cmd], cwd=ROOT, capture_output=True, text=True)
        falha = r.returncode != 0 or ("FALHAS: nenhuma" not in r.stdout if nome == "planta G09" else False)
        print(f"[{'FALHOU' if falha else 'OK'}] {nome}")
        ok &= not falha
    print("TUDO BATE" if ok else "ALGO NÃO BATE")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main("--rapido" in sys.argv))
