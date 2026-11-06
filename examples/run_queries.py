"""Execute every query in examples/queries.sql against a package and print the first rows.
python examples/run_queries.py data/quickstart/public"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from europress_data.sdk import open_dataset  # noqa: E402

root = sys.argv[1] if len(sys.argv) > 1 else "data/quickstart/public"
con = open_dataset(root)
sql = (Path(__file__).parent / "queries.sql").read_text()
blocks = re.split(r"^-- name: ", sql, flags=re.M)[1:]
ok = 0
for b in blocks:
    name, body = b.split("\n", 1)
    q = "\n".join(l for l in body.splitlines() if not l.startswith("--")).strip().rstrip(";")
    df = con.sql(q).df()
    ok += 1
    print(f"\n=== {name} ({len(df)} rows)")
    print(df.head(5).to_string())
print(f"\n{ok}/{len(blocks)} queries executed successfully")
