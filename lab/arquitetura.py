"""G09: checagens de consistência da arquitetura AMA-P1 e desenho da planta baixa (SVG)."""
from __future__ import annotations

import math
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent


def carregar(nome="AMA-P1"):
    return yaml.safe_load(open(ROOT / "arquitetura" / f"{nome}.yaml"))


def retangulos(A):
    cw, ch = A["chip_calculo"]["dimensoes_mm"]
    hw, hh = A["fontes"]["pilha_hbm_mm"]["valor"]
    out = {}
    for k, (x, y) in A["interposer"]["posicoes"].items():
        w, h = (cw, ch) if k.startswith("C") else (hw, hh)
        out[k] = (x, y, w, h)
    return out


def checar(A):
    """Retorna (lista de falhas, métricas). Uma falha = a arquitetura não é fabricável como escrita."""
    F, M = [], {}
    cc = A["chip_calculo"]
    area_blocos = sum(b["area"] for b in cc["blocos_mm2"].values())
    cw, ch = cc["dimensoes_mm"]
    M["area_chip_mm2"] = cw * ch
    M["area_blocos_mm2"] = area_blocos
    M["ocupacao"] = area_blocos / (cw * ch)
    if area_blocos > cw * ch:
        F.append(f"blocos ({area_blocos} mm²) não cabem no chip ({cw*ch:.0f} mm²)")
    if area_blocos / (cw * ch) > 0.90:
        F.append(f"ocupação {area_blocos/(cw*ch):.0%} > 90%: sem folga para roteamento")
    if cw * ch > A["fontes"]["reticle_mm2"]["valor"]:
        F.append(f"chip de {cw*ch:.0f} mm² passa do retículo")
    if max(cw, ch) > 33 or min(cw, ch) > 26:
        F.append("chip fora da janela de exposição 26 x 33 mm")
    iw, ih = A["interposer"]["dimensoes_mm"]
    M["area_interposer_mm2"] = iw * ih
    if iw * ih > A["fontes"]["cowos_l_5_5x_mm2"]["valor"]:
        F.append("interposer maior que CoWoS-L 5,5x")
    R = retangulos(A)
    if sum(1 for k in R if k.startswith("H")) != A["pilha_hbm"]["quantidade"]:
        F.append("número de pilhas na planta difere da especificação")
    nomes = list(R)
    for i, a in enumerate(nomes):
        x, y, w, h = R[a]
        if x < 0 or y < 0 or x + w > iw or y + h > ih:
            F.append(f"{a} sai do interposer")
        for b in nomes[i + 1:]:
            X, Y, W, H = R[b]
            if x < X + W and X < x + w and y < Y + H and Y < y + h:
                F.append(f"{a} sobrepõe {b}")
            else:
                gx = max(X - (x + w), x - (X + W))
                gy = max(Y - (y + h), y - (Y + H))
                if max(gx, gy) < 0.3:
                    F.append(f"{a} e {b} a menos de 0,3 mm (montagem e underfill)")
    # cada pilha precisa encostar (<= 1,5 mm) numa borda LONGA de algum chip de cálculo, e essa borda não pode ter > 3 pilhas
    bordas = {}
    for k, (x, y, w, h) in R.items():
        if not k.startswith("H"):
            continue
        ok = False
        for c in ("C0", "C1"):
            X, Y, W, H = R[c]
            sobre_x = min(x + w, X + W) - max(x, X)
            if sobre_x >= 0.5 * w:
                gap_baixo = Y - (y + h)
                gap_cima = y - (Y + H)
                for lado, gap in (("baixo", gap_baixo), ("cima", gap_cima)):
                    if 0 <= gap <= 1.5:
                        ok = True
                        bordas.setdefault((c, lado), []).append(k)
        if not ok:
            F.append(f"{k} não encosta numa borda longa de chip de cálculo (regra das 2 bordas)")
    for (c, lado), hs in bordas.items():
        if len(hs) > 3:
            F.append(f"borda {lado} de {c} com {len(hs)} pilhas (máx 3 em 33 mm)")
    M["pilhas_por_borda"] = {f"{c}-{l}": len(h) for (c, l), h in bordas.items()}
    # rendimento por chip (Poisson) e fator de custo vs o 0,65 embutido em p_mm2
    d0 = A["fontes"]["d0_defeitos_cm2"]["valor"]
    y = math.exp(-cw * ch / 100 * d0)
    M["rendimento_chip"] = y
    M["fator_custo_silicio"] = 0.65 / y
    # potência e densidade
    pw = cc["potencia_w"]
    p_chip = sum(pw.values())
    M["w_mm2_chip"] = p_chip / (cw * ch)
    if M["w_mm2_chip"] > 1.0:
        F.append("densidade de potência do chip > 1 W/mm²")
    ph = A["pilha_hbm"]["base_ama_por_pilha"]
    p_pacote = cc["quantidade"] * p_chip + A["pilha_hbm"]["quantidade"] * (ph["potencia_logica_w"] + ph["potencia_dram_w"])
    lp = A["placa"]["lpddr5x"]
    p_placa = p_pacote + lp["quantidade"] * lp["potencia_w"]
    M["potencia_pacote_w"] = p_pacote
    M["potencia_placa_w"] = p_placa
    v = A["placa"]["vrm"]
    corrente = p_pacote / v["tensao_nucleo_v"]
    M["corrente_nucleo_a"] = corrente
    if corrente > v["fases"] * v["a_por_fase"] * 0.8:
        F.append(f"VRM: {corrente:.0f} A > 80% de {v['fases']} fases x {v['a_por_fase']} A")
    sw, sh = A["placa"]["substrato_mm"]
    if iw + 10 > sw or ih + 10 > sh:
        F.append("interposer + 5 mm de borda não cabe no substrato")
    ow, oh = A["fontes"]["oam_mm"]["valor"]
    if sw > ow or sh > oh:
        F.append("substrato não cabe no OAM")
    return F, M


def svg(A, caminho):
    R = retangulos(A)
    iw, ih = A["interposer"]["dimensoes_mm"]
    s = 10
    cores = {"C": "#0061E2", "H": "#FFDE00"}
    el = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="-20 -40 {iw*s+40} {ih*s+80}" font-family="sans-serif">',
          f'<rect x="0" y="0" width="{iw*s}" height="{ih*s}" fill="#f2f2f2" stroke="#555"/>',
          f'<text x="0" y="-15" font-size="16">AMA-P1 — interposer CoWoS-L {iw:.0f} x {ih:.0f} mm (vista de cima)</text>']
    for k, (x, y, w, h) in R.items():
        yy = (ih - y - h) * s
        el.append(f'<rect x="{x*s}" y="{yy}" width="{w*s}" height="{h*s}" fill="{cores[k[0]]}" stroke="#222"/>')
        rot = f"{k} chip de cálculo {w:.0f}x{h:.0f}" if k.startswith("C") else f"{k} HBM4E+AMA"
        cor_t = "#fff" if k.startswith("C") else "#222"
        el.append(f'<text x="{(x+w/2)*s}" y="{yy+h*s/2}" font-size="{14 if k.startswith("C") else 11}" fill="{cor_t}" text-anchor="middle">{rot}</text>')
    el.append(f'<text x="0" y="{ih*s+25}" font-size="12">Bordas curtas externas: rede 224G e LPDDR5X. Borda interna C0–C1: ligação entre chips. Microcanais sob as pilhas.</text>')
    el.append("</svg>")
    Path(caminho).write_text("\n".join(el))


if __name__ == "__main__":
    A = carregar()
    F, M = checar(A)
    svg(A, ROOT / "arquitetura" / "AMA-P1_planta.svg")
    print("FALHAS:", F or "nenhuma")
    for k, v in M.items():
        print(f"  {k}: {v:.3f}" if isinstance(v, float) else f"  {k}: {v}")
