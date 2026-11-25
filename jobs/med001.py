"""MED001: mede Z (pre_gap) e L_out por fonte, conforme prereg/MED001.yaml."""
from __future__ import annotations

import json
import random
import statistics as st
from collections import defaultdict
from pathlib import Path

import pyarrow.parquet as pq

from lab.guards import salvar_resultado
from lab.manifest import run_job
from lab.params import prereg_travado

ROOT = Path(__file__).resolve().parent.parent
MAPA = {"swebench": "W1", "gaia": "W2", "wildclaw": "W3"}


def q(v, x):
    v = sorted(v)
    return v[min(len(v) - 1, int(x * (len(v) - 1)))]


def resumo(v):
    return {"n": len(v), "media": st.fmean(v), "mediana": q(v, .5), "p90": q(v, .9), "p99": q(v, .99)}


def medir(inputs, seed):
    rows = inputs["rows"]
    por_fonte = defaultdict(lambda: defaultdict(list))   # fonte -> modelo -> [(sessao, z, l)]
    for sid, mod, z, l in rows:
        fonte = sid.split("__")[0]
        por_fonte[fonte][mod].append((sid, z, l))
    out = {}
    rng = random.Random(seed)
    for fonte, mods in por_fonte.items():
        todos = [r for v in mods.values() for r in v]
        # descarta 1ª iteração de cada sessão: pre_gap == 0 e primeira ocorrência
        vistos, zs, ls, por_sessao = set(), [], [], defaultdict(list)
        for sid, z, l in todos:
            ls.append(l)
            if sid not in vistos:
                vistos.add(sid)
                continue
            zs.append(z)
            por_sessao[sid].append(z)
        medias_modelo = {}
        for mod, v in mods.items():
            vs, zz = set(), []
            for sid, z, _ in v:
                if sid in vs:
                    zz.append(z)
                vs.add(sid)
            if zz:
                medias_modelo[mod] = st.fmean(zz)
        if len(medias_modelo) >= 2:
            lo, hi, metodo = min(medias_modelo.values()), max(medias_modelo.values()), "min/max entre modelos"
        else:
            sess = list(por_sessao.values())
            boots = []
            for _ in range(2000):
                amostra = [z for s in (rng.choice(sess) for _ in sess) for z in s]
                boots.append(st.fmean(amostra))
            lo, hi, metodo = q(boots, .025), q(boots, .975), "IC95 bootstrap por sessão"
        out[fonte] = {"workload": MAPA.get(fonte), "Z_s": resumo(zs), "L_out": resumo(ls),
                      "Z_faixa_media": {"low": lo, "high": hi, "metodo": metodo},
                      "Z_media_por_modelo": medias_modelo, "sessoes": len(vistos)}
    return out


def _arred(x):
    if isinstance(x, float):
        return round(x, 4)
    if isinstance(x, dict):
        return {k: _arred(v) for k, v in x.items()}
    return x


if __name__ == "__main__":
    assert prereg_travado("MED001")
    t = pq.read_table(ROOT / "data" / "lmcache_timing.parquet").to_pydict()
    rows = list(zip(t["session_id"], t["model"], t["pre_gap"], t["output_length"]))
    man = run_job("MED001", lambda i, s: _arred(medir(i, s)), {"rows": rows}, seed=20261125)
    import sys as _s
    rev = _s.argv[1] if len(_s.argv) > 1 else ""
    salvar_resultado(ROOT / "results" / f"MED001{rev}.json", man.to_json())
    print(json.dumps(man.outputs, indent=1, ensure_ascii=False))
