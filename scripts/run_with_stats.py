"""Run a module CLI and report wall time and peak RSS (self + workers). python scripts/run_with_stats.py europress_data.generate --profile enterprise --workers 2"""
import json
import resource
import importlib
import sys
import time

mod = sys.argv[1]
sys.argv = [mod] + sys.argv[2:]
t0 = time.time()
code = 0
try:
    code = importlib.import_module(mod).main(sys.argv[1:]) or 0
except SystemExit as e:
    code = e.code or 0
st = {"module": mod, "args": sys.argv[1:], "wall_seconds": round(time.time() - t0, 1),
      "peak_rss_main_mb": round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1),
      "peak_rss_largest_child_mb": round(resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss / 1024, 1), "exit_code": code}
print("RUNSTATS " + json.dumps(st))
if "--profile" in st["args"]:
    from pathlib import Path
    prof = st["args"][st["args"].index("--profile") + 1]
    out = Path(__file__).resolve().parents[1] / "reports" / f"runstats_{prof}.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(st))
sys.exit(code)
