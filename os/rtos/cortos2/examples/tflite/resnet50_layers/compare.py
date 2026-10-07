#!/usr/bin/env python3
"""Compare two sweep variants: per-config speedup and topology-weighted total.

  ./compare.py <base> <variant>     reads results/<base>.csv, results/<variant>.csv

Refuses (exit 1) if any variant row is not ok or its checksum differs from
golden_checksums.tsv (or, without a golden file, from the base row): a
faster kernel that changes int8 outputs is a bug, not a speedup.
"""
import csv
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def load(name):
  p = HERE / "results" / f"{name}.csv"
  with open(p) as f:
    return {(int(r["op"]), int(r["rows"])): r for r in csv.DictReader(f)}


def golden():
  p = HERE / "golden_checksums.tsv"
  if not p.exists():
    return {}
  with open(p) as f:
    return {(int(r["op"]), int(r["rows"])): r["checksum"]
            for r in csv.DictReader(f, delimiter="\t")}


def main() -> int:
  if len(sys.argv) != 3:
    sys.exit(__doc__)
  base, var = load(sys.argv[1]), load(sys.argv[2])
  gold = golden()
  bad = []
  for key, v in var.items():
    want = gold.get(key) or base.get(key, {}).get("checksum")
    if v["status"] != "ok":
      bad.append(f"L{key[0]} R{key[1]}: status {v['status']}")
    elif want and v["checksum"] != want:
      bad.append(f"L{key[0]} R{key[1]}: checksum {v['checksum']} != {want}")
  if bad:
    print("compare: refusing, variant output differs:\n  " + "\n  ".join(bad))
    return 1

  with open(HERE / "layers.tsv") as f:
    layers = list(csv.DictReader(f, delimiter="\t"))
  rep = {r["config"]: int(r["op"]) for r in layers if r["rep"] == "1"}
  full = {}
  for r in layers:
    full[r["config"]] = full.get(r["config"], 0) + int(r["work"])

  print(f"{'config':<44} {'base cyc/u':>11} {'var cyc/u':>11} {'speedup':>8}"
        f" {'d I$miss':>9} {'d D$miss':>9}")
  tb = tv = 0.0
  for cfg, op in sorted(rep.items(), key=lambda kv: kv[1]):
    b, v = base.get((op, 1)), var.get((op, 1))
    if not b or not v:
      continue
    bu, vu = float(b["cycles_per_unit"]), float(v["cycles_per_unit"])
    tb += bu * full[cfg]
    tv += vu * full[cfg]
    di = int(v["prog_icache_misses"]) - int(b["prog_icache_misses"])
    dd = int(v["prog_dcache_misses"]) - int(b["prog_dcache_misses"])
    print(f"{cfg:<44} {bu:>11.3f} {vu:>11.3f} {bu / vu:>7.2f}x {di:>9} {dd:>9}")
  if tv:
    print(f"\ntopology total: base {tb:.6g}  variant {tv:.6g} cycles  "
          f"speedup {tb / tv:.3f}x  (configs present in both)")
  return 0


if __name__ == "__main__":
  sys.exit(main())
