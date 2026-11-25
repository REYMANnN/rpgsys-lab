"""Registro de execução: todo job do laboratório produz um manifesto auditável.

O manifesto grava o que é preciso para reproduzir e auditar uma rodada:
versão do código (commit), ambiente (Python, plataforma), semente,
hash SHA-256 de cada entrada e de cada saída, e o tempo de execução.
"""
from __future__ import annotations

import hashlib
import json
import os
import platform
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Callable


def sha256_of(obj: Any) -> str:
    """Hash canônico de um objeto JSON (chaves ordenadas, sem espaços)."""
    payload = json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def git_commit() -> str:
    env = os.environ.get("LAB_GIT_COMMIT") or os.environ.get("GITHUB_SHA")
    if env:
        return env
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], stderr=subprocess.DEVNULL, text=True).strip()
    except Exception:
        return "desconhecido"


@dataclass
class Manifest:
    job: str
    seed: int
    inputs_sha256: str
    outputs_sha256: str
    commit: str
    runner: str
    python: str
    platform: str
    seconds: float
    outputs: dict = field(default_factory=dict)

    def to_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, indent=2, ensure_ascii=False, default=str)


def run_job(name: str, fn: Callable[[dict, int], dict], inputs: dict, seed: int, runner: str = "local") -> Manifest:
    """Executa fn(inputs, seed) e devolve o manifesto da execução."""
    t0 = time.perf_counter()
    outputs = fn(inputs, seed)
    dt = time.perf_counter() - t0
    return Manifest(
        job=name,
        seed=seed,
        inputs_sha256=sha256_of(inputs),
        outputs_sha256=sha256_of(outputs),
        commit=git_commit(),
        runner=runner,
        python=sys.version.split()[0],
        platform=platform.platform(),
        seconds=round(dt, 6),
        outputs=outputs,
    )
