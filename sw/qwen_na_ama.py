"""SW001: Qwen3-0.6B com a atenção de decodificação no simulador da AMA (prereg/SW001.yaml)."""
from __future__ import annotations

import json
import math
import sys
import time
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as Fn
from transformers import AutoModelForCausalLM, AutoTokenizer, AttentionInterface
from transformers.integrations.sdpa_attention import sdpa_attention_forward

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from rtl.ama_pista import F  # noqa: E402
from sw.ama_numpy import pistas  # noqa: E402
from lab.guards import salvar_resultado  # noqa: E402
from lab.manifest import run_job  # noqa: E402
from lab.params import prereg_travado  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DESLOC = 16
ESTADO = {"escalas": {}, "modo": "ref", "braco": "SW001"}

TEXTOS = [
    "O Banco Central do Brasil é responsável pela política monetária do país. Ele define a taxa básica de juros, "
    "a Selic, em reuniões do Comitê de Política Monetária, que acontecem a cada quarenta e cinco dias. A decisão leva em "
    "conta a inflação corrente, as expectativas do mercado, a atividade econômica e o cenário externo. Quando a inflação "
    "está acima da meta, o comitê tende a subir os juros para conter a demanda; quando está abaixo, pode reduzi-los para "
    "estimular o crédito e o consumo. As pequenas empresas sentem esses movimentos rapidamente, porque dependem de capital "
    "de giro de curto prazo e pagam taxas bem maiores que as grandes companhias. Por isso, muitas lojas de bairro, "
    "farmácias e mercados pequenos acompanham de perto as decisões do Copom e ajustam estoques, prazos e preços conforme o "
    "custo do dinheiro muda ao longo do ano, buscando preservar o caixa e a margem.",
    "The transistor is the fundamental building block of modern electronics. Invented at Bell Labs in 1947, it replaced "
    "vacuum tubes and made computers smaller, cheaper and far more reliable. A modern processor contains tens of billions "
    "of transistors, each switching billions of times per second. As transistors shrank, engineers ran into new limits: "
    "leakage current, heat density and the cost of lithography. Memory became a bottleneck too, because moving data from "
    "DRAM to the processor costs much more energy than computing on it. This is why designers now stack memory dies, place "
    "them next to the logic on silicon interposers, and increasingly push simple computation into the memory itself. The "
    "trend toward specialized accelerators reflects the same idea: do the common case well, and spend energy only where it "
    "matters most for the workload at hand.",
    "def online_softmax(scores, values):\n    m = float('-inf')\n    l = 0.0\n    acc = [0.0] * len(values[0])\n"
    "    for s, v in zip(scores, values):\n        m_new = max(m, s)\n        a = math.exp(m - m_new)\n        b = math.exp(s - m_new)\n"
    "        l = l * a + b\n        acc = [x * a + b * y for x, y in zip(acc, v)]\n        m = m_new\n    return [x / l for x in acc]\n\n"
    "def attention(q, keys, values, scale):\n    scores = [sum(a * b for a, b in zip(q, k)) * scale for k in keys]\n"
    "    return online_softmax(scores, values)\n\n# The function above processes one token at a time and never stores the full\n"
    "# probability vector, which is exactly what makes it suitable for hardware next to memory.\n",
]


def ama_attention(module, query, key, value, attention_mask, scaling=None, dropout=0.0, **kw):
    if ESTADO["modo"] == "ama" and ESTADO["braco"] == "FP8" and query.shape[2] == 1:
        sk, sv, _ = ESTADO["escalas"][module.layer_idx]
        f8 = torch.float8_e4m3fn
        ks = (sk * 127 / 448)[None, :, None, None]
        vs = (sv * 127 / 448)[None, :, None, None]
        k8 = (key.float() / ks).clamp(-448, 448).to(f8).float() * ks
        v8 = (value.float() / vs).clamp(-448, 448).to(f8).float() * vs
        return sdpa_attention_forward(module, query, k8.to(key.dtype), v8.to(value.dtype), attention_mask, scaling=scaling, dropout=dropout, **kw)
    if ESTADO["modo"] == "ref" or query.shape[2] != 1:
        if query.shape[2] > 1:   # prefill: mede escalas fixas de K e V por camada/cabeça
            ESTADO["escalas"][module.layer_idx] = (
                key[0].abs().amax(dim=(1, 2)).float() * 1.25 / 127, value[0].abs().amax(dim=(1, 2)).float() * 1.25 / 127,
                key[0].abs().amax(dim=1).float().clamp_min(1e-6) * 1.25 / 127)   # (Hkv, dh): por canal (SW002)
        return sdpa_attention_forward(module, query, key, value, attention_mask, scaling=scaling, dropout=dropout, **kw)
    sk, sv, skc = ESTADO["escalas"][module.layer_idx]
    braco = ESTADO["braco"]
    Hq, Hkv, dh = query.shape[1], key.shape[1], query.shape[3]
    g = Hq // Hkv
    q = query[0, :, 0, :].float()                          # (Hq, dh)
    K = key[0].float()                                     # (Hkv, T, dh)
    V = value[0].float()
    vexp = None
    if braco == "SW001":
        Ki = torch.clamp(torch.round(K / sk[:, None, None]), -128, 127)
        skq = np.repeat(sk.numpy(), g)
    else:   # K por canal; a escala do canal é dobrada na consulta
        Ki = torch.clamp(torch.round(K / skc[:, None, :]), -128, 127)
        q = q * torch.repeat_interleave(skc, g, dim=0)
        skq = np.ones(Hq)
    sq = q.abs().amax(dim=1).clamp_min(1e-12) / 127
    qi = torch.clamp(torch.round(q / sq[:, None]), -128, 127).numpy().astype(np.int64)
    if braco == "B":    # V com expoente por token (potência de 2)
        vmax = V.abs().amax(dim=2)                         # (Hkv, T)
        base = (vmax.amin(dim=1).clamp_min(1e-6) / 127)    # menor escala da cabeça
        e = torch.clamp(torch.ceil(torch.log2((vmax / 127) / base[:, None]).clamp_min(0)), 0, 15)   # (Hkv, T)
        Vi = torch.clamp(torch.round(V / (base[:, None, None] * 2 ** e[:, :, None])), -128, 127)
        vexp = np.repeat(e.numpy().astype(np.int64), g, axis=0).T     # (T, Hq)
        svq = np.repeat(base.numpy(), g)
    else:
        Vi = torch.clamp(torch.round(V / sv[:, None, None]), -128, 127)
        svq = np.repeat(sv.numpy(), g)
    Ki = np.repeat(Ki.numpy().astype(np.int64), g, axis=0).transpose(1, 0, 2)       # (T, Hq, dh)
    Vi = np.repeat(Vi.numpy().astype(np.int64), g, axis=0).transpose(1, 0, 2)
    real = sq.numpy() * skq * scaling * math.log2(math.e) * (2 ** F)
    # desloc por pista (5 bits no RTL) escolhido para a escala caber em 16 bits sem saturar
    desloc = np.clip(np.floor(np.log2(65535 / np.maximum(real, 1e-30))), 0, 31).astype(np.int64)
    escala = np.clip(np.round(real * 2.0 ** desloc), 1, 65535).astype(np.int64)
    ESTADO.setdefault("diag", []).append(float(np.max(np.abs(escala / 2.0 ** desloc - real) / real)))
    m, l, o = pistas(qi, Ki, Vi, escala, desloc, vexp)
    out = torch.from_numpy((o / l[:, None]) * svq[:, None]).float()   # divisão final no chip de cálculo
    return out[None, None, :, :].to(query.dtype), None             # (B, T=1, Hq, dh)


AttentionInterface.register("ama", ama_attention)


def avaliar(modelo, tok, texto, n_prompt=128, n_aval=128):
    ids = tok(texto, return_tensors="pt").input_ids[0][: n_prompt + n_aval]
    n_aval = len(ids) - n_prompt
    res = {}
    for modo in ("ref", "ama"):
        ESTADO["modo"] = modo
        with torch.no_grad():
            out = modelo(ids[None, :n_prompt], use_cache=True)
            cache = out.past_key_values
            logits = [out.logits[0, -1]]
            for t in range(n_prompt, n_prompt + n_aval - 1):
                out = modelo(ids[None, t:t + 1], past_key_values=cache, use_cache=True)
                cache = out.past_key_values
                logits.append(out.logits[0, -1])
        res[modo] = torch.stack(logits).float()
    alvo = ids[n_prompt:n_prompt + n_aval]
    lr, la = Fn.log_softmax(res["ref"], -1), Fn.log_softmax(res["ama"], -1)
    nll_r = -lr[torch.arange(n_aval), alvo].mean().item()
    nll_a = -la[torch.arange(n_aval), alvo].mean().item()
    return {"tokens": n_aval, "top1": (res["ref"].argmax(-1) == res["ama"].argmax(-1)).float().mean().item(),
            "kl": (lr.exp() * (lr - la)).sum(-1).mean().item(), "ppl_ref": math.exp(nll_r), "ppl_ama": math.exp(nll_a),
            "ppl_rel": math.exp(nll_a) / math.exp(nll_r) - 1}


def rodar(inputs, seed):
    torch.manual_seed(seed)
    tok = AutoTokenizer.from_pretrained("Qwen/Qwen3-0.6B")
    modelo = AutoModelForCausalLM.from_pretrained("Qwen/Qwen3-0.6B", torch_dtype=torch.float32, attn_implementation="ama")
    modelo.eval()
    t0 = time.time()
    trechos = [avaliar(modelo, tok, x) for x in TEXTOS]
    top1 = sum(t["top1"] for t in trechos) / 3
    ppl = sum(t["ppl_rel"] for t in trechos) / 3
    return {"trechos": trechos, "top1_medio": top1, "ppl_rel_medio": ppl, "segundos": time.time() - t0,
            "veredito": "APROVADO" if top1 >= 0.97 and ppl <= 0.03 else "REPROVADO"}


if __name__ == "__main__":
    camp = sys.argv[1] if len(sys.argv) > 1 else "SW001"
    braco = sys.argv[2] if len(sys.argv) > 2 else "SW001"
    assert prereg_travado(camp)
    ESTADO["braco"] = braco
    nome = camp if camp == "SW001" else f"{camp}{braco}"
    man = run_job(nome, rodar, {"textos": TEXTOS, "modelo": "Qwen/Qwen3-0.6B", "desloc": DESLOC, "braco": braco}, seed=0)
    salvar_resultado(ROOT / "results" / f"{nome}.json", man.to_json())
    print(json.dumps({k: v for k, v in man.outputs.items() if k != "trechos"}, indent=1))
    for t in man.outputs["trechos"]:
        print(t)
