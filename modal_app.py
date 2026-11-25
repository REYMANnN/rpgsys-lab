"""Roda o mesmo job de fumaça no Modal e devolve o manifesto.

Uso (com MODAL_TOKEN_ID e MODAL_TOKEN_SECRET no ambiente):
    modal run modal_app.py
"""
import json
import os

import modal

image = (
    modal.Image.debian_slim(python_version="3.12")
    .env({"LAB_GIT_COMMIT": os.environ.get("GITHUB_SHA", "local")})
    .add_local_python_source("lab", "jobs")
)
app = modal.App("rpgsys-lab-smoke", image=image)


@app.function(timeout=600)
def smoke(seed: int = 42) -> str:
    from jobs.roofline_smoke import DEFAULT_INPUTS, roofline
    from lab.manifest import run_job

    return run_job("roofline_smoke", roofline, DEFAULT_INPUTS, seed, runner="modal").to_json()


@app.local_entrypoint()
def main(seed: int = 42, out: str = "manifest_modal.json"):
    text = smoke.remote(seed)
    with open(out, "w", encoding="utf-8") as f:
        f.write(text)
    print(text)
