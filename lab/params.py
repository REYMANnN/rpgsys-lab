"""Carrega e valida a base fixa: rótulos, faixas e fontes."""
from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Iterator

import yaml

ROOT = Path(__file__).resolve().parent.parent
ROTULOS = {"MEDIDO", "PUBLICADO", "CALIBRADO", "DERIVADO", "ESTIMADO", "HIPÓTESE", "UNKNOWN"}


def load(name: str) -> dict:
    with open(ROOT / "base" / name, encoding="utf-8") as f:
        return yaml.safe_load(f)


def iter_params(tree, path: str = "") -> Iterator[tuple[str, dict]]:
    """Percorre a árvore e devolve todo dicionário que tem 'rotulo'."""
    if isinstance(tree, dict):
        if "rotulo" in tree:
            yield path, tree
        for k, v in tree.items():
            if k == "rotulo":
                continue
            yield from iter_params(v, f"{path}.{k}" if path else str(k))


def problemas(tree) -> tuple[list[str], list[str]]:
    """Devolve (erros que bloqueiam o juiz, dívidas que só são relatadas)."""
    erros, dividas = [], []
    for path, p in iter_params(tree):
        r = p["rotulo"]
        if r not in ROTULOS:
            erros.append(f"{path}: rótulo inválido {r!r}")
            continue
        lo, nom, hi = p.get("low"), p.get("nominal"), p.get("high")
        for nome_campo, x in (("low", lo), ("nominal", nom), ("high", hi), ("valor", p.get("valor"))):
            if isinstance(x, str) and re.fullmatch(r"[-+]?[0-9.]+([eE][-+]?[0-9]+)?", x.strip()):
                erros.append(f"{path}: {nome_campo} é texto numérico {x!r} (YAML não leu como número)")
        if all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in (lo, nom, hi)):
            if not lo <= nom <= hi:
                erros.append(f"{path}: faixa inconsistente low={lo} nominal={nom} high={hi}")
        if p.get("critico"):
            if r == "HIPÓTESE" and (lo is None or hi is None):
                erros.append(f"{path}: HIPÓTESE crítica sem faixa")
            if r == "PUBLICADO" and not p.get("fonte"):
                erros.append(f"{path}: PUBLICADO crítico sem fonte")
            if r == "UNKNOWN":
                erros.append(f"{path}: UNKNOWN crítico")
        elif r == "PUBLICADO" and not p.get("fonte"):
            dividas.append(f"{path}: PUBLICADO sem link de fonte")
    return erros, dividas


def prereg_hash(campanha: str) -> str:
    return hashlib.sha256((ROOT / "prereg" / f"{campanha}.yaml").read_bytes()).hexdigest()


def prereg_travado(campanha: str) -> bool:
    for line in (ROOT / "prereg" / "LOCK.txt").read_text().splitlines():
        h, _, f = line.partition("  ")
        if f.strip() == f"prereg/{campanha}.yaml":
            return h == prereg_hash(campanha)
    return False


if __name__ == "__main__":
    for nome in ("params.yaml", "workloads.yaml", "competitors.yaml"):
        e, d = problemas(load(nome))
        print(f"{nome}: {len(e)} erros, {len(d)} dívidas de fonte")
        for x in e + d:
            print("  -", x)
    print("C001 travado:", prereg_travado("C001"))
