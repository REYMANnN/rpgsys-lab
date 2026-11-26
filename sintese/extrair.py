"""Lê os relatórios do OpenROAD-flow-scripts e grava results/G11_sintese.json."""
import json, re, sys
from pathlib import Path
base = Path(sys.argv[1])
txt = "\n".join(p.read_text(errors="ignore") for p in base.rglob("*.rpt")) + "\n".join(p.read_text(errors="ignore") for p in base.rglob("*.log"))
def ach(pad, conv=float):
    m = re.findall(pad, txt)
    return conv(m[-1]) if m else None
out = {
  "area_um2": ach(r"Design area ([0-9.]+) u\^2"),
  "utilizacao_pct": ach(r"Design area [0-9.]+ u\^2 ([0-9.]+)% utilization"),
  "wns_ps": ach(r"wns (?:max )?(-?[0-9.]+)"),
  "tns_ps": ach(r"tns (?:max )?(-?[0-9.]+)"),
  "potencia_total_w": ach(r"Total\s+[0-9.e+-]+\s+[0-9.e+-]+\s+[0-9.e+-]+\s+([0-9.e+-]+)"),
  "drc_erros": ach(r"\[INFO DRT-0199\]\s+Number of violations = ([0-9]+)", int),
  "periodo_ps": 1000,
}
print(json.dumps(out, indent=1))
Path("results/G11_sintese.json").write_text(json.dumps(out, indent=1))
