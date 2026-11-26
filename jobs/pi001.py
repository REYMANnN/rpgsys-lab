"""PI001: rede de alimentação (impedância, queda DC, transitório) e orçamento de perdas de sinal (prereg/PI001.yaml)."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from lab import arquitetura as AR
from lab.guards import salvar_resultado
from lab.manifest import run_job
from lab.params import prereg_travado

ROOT = Path(__file__).resolve().parent.parent

# rede concentrada: ramos em paralelo vistos do die, cada um com R, L, C em série (ESR/ESL), mais caminho série
CENARIOS = {
    "nominal": dict(
        r_serie=12e-6,            # placa + BGA + substrato + C4 (Ω)
        vrm=dict(R=0.020e-3, L=1.5e-9 / 32, bw=300e3),  # 32 fases
        bulk=dict(n=40, C=470e-6, esr=6e-3, esl=1.2e-9),
        mlcc=dict(n=400, C=22e-6, esr=3e-3, esl=0.35e-9),
        pkg=dict(n=300, C=1e-6, esr=10e-3, esl=0.05e-9),
        die=dict(C=4e-6, esr=0.15e-3)),                 # capacitância no die (2 chips) + MIM no interposer
    "otimista": dict(r_serie=8e-6, vrm=dict(R=0.015e-3, L=1.2e-9 / 32, bw=500e3), bulk=dict(n=60, C=470e-6, esr=5e-3, esl=1e-9),
                     mlcc=dict(n=600, C=22e-6, esr=2.5e-3, esl=0.3e-9), pkg=dict(n=500, C=1e-6, esr=8e-3, esl=0.04e-9),
                     die=dict(C=8e-6, esr=0.1e-3)),
    "pessimista": dict(r_serie=18e-6, vrm=dict(R=0.030e-3, L=2e-9 / 32, bw=200e3), bulk=dict(n=30, C=470e-6, esr=8e-3, esl=1.5e-9),
                       mlcc=dict(n=300, C=22e-6, esr=4e-3, esl=0.45e-9), pkg=dict(n=200, C=1e-6, esr=12e-3, esl=0.07e-9),
                       die=dict(C=2.5e-6, esr=0.2e-3)),
}


def z_rede(f, c):
    w = 2j * np.pi * f
    def ramo(n, C, esr, esl):
        return (esr + w * esl + 1 / (w * C)) / n
    # VRM: impedância baixa até a banda de controle, depois indutiva
    # VRM com sensoriamento remoto no die: abaixo da banda de controle ele compensa a queda do caminho série;
    # o que sobra é a linha de carga (R). Acima da banda, VRM vira indutância e o caminho série aparece inteiro.
    x = f / c["vrm"]["bw"]
    z_vrm = c["vrm"]["R"] + w * c["vrm"]["L"] * (1 + x) - c["r_serie"] / (1 + x)
    placa = 1 / (1 / z_vrm + 1 / ramo(**c["bulk"]) + 1 / ramo(**c["mlcc"]))
    pacote = 1 / (1 / (placa + c["r_serie"] + w * 2e-12) + 1 / ramo(**c["pkg"]))
    die = c["die"]["esr"] + 1 / (w * c["die"]["C"])
    return 1 / (1 / pacote + 1 / die)


def transitorio(c, I, v0, dI, tr=1e-6):
    """Resposta a um degrau de corrente via FFT da impedância (sistema linear)."""
    N, T = 2 ** 16, 200e-6
    t = np.linspace(0, T, N, endpoint=False)
    i = np.clip(t / tr, 0, 1) * dI
    f = np.fft.rfftfreq(N, T / N)
    f[0] = 1.0
    Z = z_rede(f, c)
    Z[0] = c["vrm"]["R"]
    v = v0 - I * c["vrm"]["R"] - np.fft.irfft(np.fft.rfft(i) * Z, N)
    return float(v.min())


def rodar(inputs, seed):
    A = AR.carregar()
    _, M = AR.checar(A)
    I = M["corrente_nucleo_a"]
    v0 = A["placa"]["vrm"]["tensao_nucleo_v"]
    z_alvo = 0.05 * v0 / (0.5 * I)
    f = np.logspace(3, 9, 600)
    out = {"corrente_pico_a": I, "z_alvo_ohm": z_alvo}
    for nome, c in CENARIOS.items():
        z = np.abs(z_rede(f, c))
        dc = I * c["vrm"]["R"]          # com sensoriamento remoto, a queda DC no die é a linha de carga
        vmin = transitorio(c, 0.5 * I, v0, 0.5 * I)
        out[nome] = {"z_max_ohm": float(z.max()), "f_do_pico_hz": float(f[z.argmax()]), "z_ok": bool(z.max() <= z_alvo),
                     "queda_dc_pct": dc / v0 * 100, "dc_ok": dc / v0 <= 0.03,
                     "v_min_transitorio": vmin, "transitorio_ok": vmin >= v0 * 0.95}
        out[nome]["ok"] = out[nome]["z_ok"] and out[nome]["dc_ok"] and out[nome]["transitorio_ok"]
    # sinal: orçamento de perdas em 56 GHz (Nyquist do 224G PAM4) — dB
    for nome, (pkg, db_pol, pol, con, via) in {"nominal": (6.0, 1.1, 8.0, 3.0, 2.0), "otimista": (5.0, 0.9, 6.0, 2.0, 1.5),
                                               "pessimista": (7.0, 1.3, 10.0, 4.0, 3.0)}.items():
        perda = pkg + db_pol * pol + con + via
        out.setdefault("serdes_224g", {})[nome] = {"perda_db": perda, "ok": perda <= 32}
    out["lpddr5x"] = {"trilha_mm": 40, "ok": True, "nota": "8 módulos a 4 por lado curto, <= 40 mm do encapsulamento (planta)"}
    nom = out["nominal"]["ok"] and out["serdes_224g"]["nominal"]["ok"]
    oti = out["otimista"]["ok"] and out["serdes_224g"]["otimista"]["ok"]
    out["veredito"] = "APROVADO" if nom else ("ZONA_CINZA" if oti else "REPROVADO")
    return out


if __name__ == "__main__":
    assert prereg_travado("PI001")
    man = run_job("PI001", rodar, {"arquitetura": AR.carregar()}, seed=0)
    salvar_resultado(ROOT / "results" / "PI001-r1.json", man.to_json())
    print(json.dumps(man.outputs, indent=1, ensure_ascii=False, default=str))
