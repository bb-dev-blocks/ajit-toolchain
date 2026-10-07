#!/usr/bin/env python3
"""Topology total: scale per-config measured cost to every ResNet-50 op.

Each op's cost = (its config's measured invoke cost per work unit, from the
cropped harness run) × (the op's full work from layers.tsv: executed MACs for
CONV_2D/FC, output elements for most others, input elements for MEAN).

Inputs (under results/):
  <variant>.csv             C-model sweep (invoke cycles)          required
  <variant>-qemu-insn.csv   qemu invoke instructions per layer     optional
  qemu-model-insn.txt       qemu invoke instructions, full model   optional
Writes results/<variant>-per-op.csv and prints config / stage / kind tables,
the total, the weighted invoke CPI and the qemu anchor check.
"""
import argparse
import csv
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
RES = HERE / "results"
ANCHOR_GATE = 0.15


def read_csv(p: Path, delim=","):
  with open(p) as f:
    return list(csv.DictReader(f, delimiter=delim))


def per_unit(rows, value_key):
  """config/op → value per work unit, taking the smallest-ROWS ok row."""
  out = {}
  for r in sorted(rows, key=lambda r: int(r["rows"])):
    if r.get("status", "ok") != "ok" or not r.get(value_key):
      continue
    out.setdefault(int(r["op"]), (int(r[value_key]), int(r["rows"])))
  return out


def main() -> int:
  ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
  ap.add_argument("--variant", default="reference")
  a = ap.parse_args()
  layers = read_csv(HERE / "layers.tsv", "\t")
  sweep = read_csv(RES / f"{a.variant}.csv")
  work_of = {int(r["op"]): int(r["work"]) for r in sweep if r.get("work")}
  cyc = per_unit(sweep, "invoke_cycles")
  qpath = RES / f"{a.variant}-qemu-insn.csv"
  ins = per_unit(read_csv(qpath), "invoke_insns") if qpath.exists() else {}

  rep_of = {r["config"]: int(r["op"]) for r in layers if r["rep"] == "1"}
  missing = sorted({c for c in rep_of if rep_of[c] not in cyc})
  if missing:
    print("estimate: no ok C-model row for configs: " + ", ".join(missing),
          file=sys.stderr)
    return 1

  per_op, by = [], {k: defaultdict(lambda: [0, 0, 0]) for k in
                    ("config", "stage", "kind")}
  tot_c = tot_i = 0
  for r in layers:
    rep = rep_of[r["config"]]
    full = int(r["work"])
    c_unit = cyc[rep][0] / work_of[rep]
    cycles = c_unit * full
    insns = ins[rep][0] / work_of[rep] * full if rep in ins else None
    per_op.append(dict(op=r["op"], kind=r["kind"], config=r["config"],
                       stage=r["stage"], work=full, work_unit=r["work_unit"],
                       rep_op=rep, cycles_per_unit=round(c_unit, 3),
                       cycles=round(cycles),
                       insns=round(insns) if insns is not None else ""))
    tot_c += cycles
    tot_i += insns or 0
    for k in by:
      b = by[k][r[k]]
      b[0] += 1
      b[1] += cycles
      b[2] += insns or 0

  with open(RES / f"{a.variant}-per-op.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(per_op[0]))
    w.writeheader()
    w.writerows(per_op)

  have_i = len(ins) >= len(rep_of) and all(rep_of[c] in ins for c in rep_of)
  for k in ("config", "stage", "kind"):
    print(f"\n{k:<44} {'ops':>4} {'cycles':>16} {'%':>6}"
          + (f" {'CPI':>6}" if have_i else ""))
    for name, (n, c, i) in sorted(by[k].items(), key=lambda kv: -kv[1][1]):
      print(f"{name:<44} {n:>4} {c:>16.4g} {100 * c / tot_c:>6.2f}"
            + (f" {c / i:>6.3f}" if have_i and i else ""))
  print(f"\ntotal invoke cycles (C-model, {a.variant}): {tot_c:.6g}")
  macs = sum(int(r["work"]) for r in layers if r["work_unit"] == "mac")
  print(f"cycles per executed MAC (all ops / MACs): {tot_c / macs:.2f}")

  status = 0
  if have_i:
    print(f"estimated invoke instructions: {tot_i:.6g}; "
          f"weighted invoke CPI: {tot_c / tot_i:.4f}")
    mpath = RES / "qemu-model-insn.txt"
    if mpath.exists():
      q = int(mpath.read_text().split()[1])
      gap = (tot_i - q) / q
      print(f"qemu full-model invoke instructions: {q:.6g}; "
            f"topology-sum gap {100 * gap:+.2f}% "
            f"({'ok' if abs(gap) <= ANCHOR_GATE else 'OVER GATE'} "
            f"±{ANCHOR_GATE:.0%})")
      print(f"anchor total = qemu instructions × weighted CPI: "
            f"{q * tot_c / tot_i:.6g} cycles")
      status = 0 if abs(gap) <= ANCHOR_GATE else 1
  return status


if __name__ == "__main__":
  sys.exit(main())
