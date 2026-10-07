#!/usr/bin/env python3
"""Collect C-model layer logs into one results CSV (one row per op/rows).

Reads logs/<variant>/L<op>_R<rows>.log, layers.tsv and the job's work dir.
Non-reference variants are checked against golden_checksums.tsv; any failed
run or checksum mismatch → exit 1 (rows are still written, status column).
"""
import argparse
import csv
import importlib.util
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location(
    "cmodel_metrics", HERE.parent / "cmodel_metrics.py")
cm = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cm)

GOLDEN = HERE / "golden_checksums.tsv"
HALT = ["instructions", "cycles", "cpi", "traps", "cti", "cti_mispredicts",
        "tlb_misses", "icache_accesses", "icache_misses", "dcache_accesses",
        "dcache_misses", "dcache_read_misses", "dcache_write_misses", "wall_s"]
FIELDS = (["variant", "op", "rows", "config", "kind", "stage", "work",
           "work_unit", "invoke_cycles", "cycles_per_unit", "checksum",
           "status"] + [f"prog_{k}" for k in HALT] + ["tflm_rev", "cmodel_cmd"])


def load_layers():
  with open(HERE / "layers.tsv") as f:
    return {int(r["op"]): r for r in csv.DictReader(f, delimiter="\t")}


def load_golden():
  if not GOLDEN.exists():
    return {}
  with open(GOLDEN) as f:
    return {(int(r["op"]), int(r["rows"])): r["checksum"]
            for r in csv.DictReader(f, delimiter="\t")}


def cmodel_cmd(work: Path) -> str:
  p = work / "cortos_build" / "run_cmodel.sh"
  if not p.exists():
    return ""
  m = re.search(r"^(ajit_C_system_model.*?);", p.read_text(), re.S | re.M)
  return " ".join(m.group(1).replace("\\", " ").split()) if m else ""


def row_for(variant, op, rows, layers, golden):
  work = HERE / "work" / variant / f"L{op}_R{rows}"
  log = HERE / "logs" / variant / f"L{op}_R{rows}.log"
  lay = layers[op]
  r = dict(variant=variant, op=op, rows=rows, config=lay["config"],
           kind=lay["kind"], stage=lay["stage"], status="ok")
  rev = work / "tflm_rev"
  r["tflm_rev"] = rev.read_text().strip() if rev.exists() else ""
  r["cmodel_cmd"] = cmodel_cmd(work)
  try:
    m = cm.parse(log.read_text(errors="replace"))
  except (OSError, ValueError) as e:
    r["status"] = f"no-stats: {e}"
    return r
  for k in HALT:
    r[f"prog_{k}"] = m.get(k, "")
  layer = dict(kv.split("=", 1) for kv in m.get("app_layer", "").split())
  r["work"], r["work_unit"] = layer.get("work", ""), layer.get("unit", "")
  r["invoke_cycles"] = m.get("app_cycles", "")
  r["checksum"] = m.get("app_checksum", "")
  text = log.read_text(errors="replace")
  if "invoke: ok" not in text or not r["invoke_cycles"]:
    r["status"] = "invoke-failed"
  elif r["work"]:
    r["cycles_per_unit"] = round(int(r["invoke_cycles"]) / int(r["work"]), 3)
  want = golden.get((op, rows))
  if variant != "reference" and r["status"] == "ok":
    if want is None:
      r["status"] = "no-golden"
    elif want != r["checksum"]:
      r["status"] = f"checksum-mismatch (golden {want})"
  return r


def main() -> int:
  ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
  ap.add_argument("--variant", default="reference")
  ap.add_argument("--out", type=Path, required=True)
  ap.add_argument("--write-golden", action="store_true")
  ap.add_argument("entries", nargs="+", help="op or op:rows")
  a = ap.parse_args()
  layers, golden = load_layers(), load_golden()
  rows = []
  for e in a.entries:
    op, _, n = e.partition(":")
    rows.append(row_for(a.variant, int(op), int(n or 1), layers, golden))
  out = HERE / a.out
  out.parent.mkdir(parents=True, exist_ok=True)
  with open(out, "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
    w.writeheader()
    w.writerows(rows)
  bad = [r for r in rows if r["status"] != "ok"]
  if a.write_golden and not bad:
    with open(GOLDEN, "w") as f:
      f.write("op\trows\tconfig\tchecksum\n")
      for r in rows:
        f.write(f"{r['op']}\t{r['rows']}\t{r['config']}\t{r['checksum']}\n")
  for r in rows:
    print(f"L{r['op']:<3} R{r['rows']} {r['kind']:<16} "
          f"{r.get('cycles_per_unit', ''):>10} cyc/{r.get('work_unit', '')}  "
          f"{r.get('checksum', '')}  {r['status']}")
  print(f"collect: {len(rows)} rows → {a.out}"
        + (f"; {len(bad)} not ok" if bad else ""))
  return 1 if bad else 0


if __name__ == "__main__":
  sys.exit(main())
