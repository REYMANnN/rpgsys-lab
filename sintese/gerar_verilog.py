"""Exporta a pista da AMA para Verilog (entrada da síntese)."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from amaranth.back import verilog  # noqa: E402
from rtl.ama_pista import AmaPista  # noqa: E402

d = AmaPista()
Path(__file__).with_name("ama_pista.v").write_text(verilog.convert(d, name="ama_pista"))
print("ok")
