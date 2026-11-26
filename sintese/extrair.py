"""Lê o 6_report.json do OpenROAD-flow-scripts e grava results/G11_sintese.json."""
import json, sys
from pathlib import Path
base = Path(sys.argv[1])
r = json.loads(next(base.rglob("6_report.json")).read_text())
drc = next(base.rglob("5_route_drc.rpt"), None)
out = {
  "plataforma": "ASAP7 (7 nm preditivo, aberto)", "alvo_periodo_ps": 1000,
  "area_celulas_um2": r["finish__design__instance__area"], "area_die_um2": r["finish__design__die__area"],
  "utilizacao": r["finish__design__instance__utilization"],
  "setup_wns_ps": r["finish__timing__setup__ws"], "hold_wns_ps": r["finish__timing__hold__ws"],
  "fmax_mhz": r["finish__timing__fmax"] / 1e6, "potencia_w_no_alvo": r["finish__power__total"],
  "queda_ir_pior_v": r["finish__design_powergrid__drop__worst__net:VDD__corner:default"],
  "drc_violacoes": 0 if drc is None or not drc.read_text().strip() else len(drc.read_text().splitlines()),
  "gds": "results/sintese_asap7/6_final.gds.gz",
}
print(json.dumps(out, indent=1))
Path("results/G11_sintese.json").write_text(json.dumps(out, indent=1))
