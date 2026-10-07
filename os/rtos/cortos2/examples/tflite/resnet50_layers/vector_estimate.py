#!/usr/bin/env python3
"""Analytic ISA v2 SIMD speedup estimate from the measured reference sweep.

  ./vector_estimate.py --assumptions vector_assumptions.yaml [--scenario NAME]

Reads layers.tsv, results/<base>.csv (C-model invoke cycles) and
results/<base>-qemu-insn.csv (qemu invoke instructions); the model is
described in the assumptions file. Prints per-config cycles and the total
per scenario with speedup over the measured reference.
"""
import argparse
import csv
import sys
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
MAC_KINDS = ("CONV_2D", "FULLY_CONNECTED")


def read(p, delim=","):
  with open(p) as f:
    return list(csv.DictReader(f, delimiter=delim))


def count(shape):
  n = 1
  for x in shape.split("x"):
    n *= int(x)
  return n


def op_cycles(s, split, kind, macs, outs, ins, ref_cyc, ref_ins):
  """Model cycles for one op given its full-size reference cycles/insns."""
  if kind not in MAC_KINDS:
    return ref_cyc * s["other_ops_scale"]
  inner = s["inner_insns_per_mac"]
  if inner == "measured":
    inner = ref_ins / macs
  insns = (macs * inner + outs * s["per_output_insns"]
           + ins * s["widen_insns_per_input"])
  vec_extra = macs / s["macs_per_vector_op"] * (s["vector_op_cycles"] - 1)
  stall_scale = (split["mispredict"] * insns / ref_ins
                 + split["icache"] * s["icache_scale"]
                 + split["dcache"] * s["dcache_scale"])
  return insns + vec_extra + (ref_cyc - ref_ins) * stall_scale


def main() -> int:
  ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
  ap.add_argument("--assumptions", type=Path, required=True)
  ap.add_argument("--scenario", action="append",
                  help="limit to these scenarios (repeatable)")
  ap.add_argument("--base", default="reference")
  ap.add_argument("--per-config", action="store_true",
                  help="print the per-config table for each scenario")
  a = ap.parse_args()
  spec = yaml.safe_load(a.assumptions.read_text())
  scen, split = spec["scenarios"], spec["reference_stall_split"]
  names = a.scenario or list(scen)
  for n in names:
    if n not in scen:
      sys.exit(f"vector_estimate: unknown scenario {n}")

  layers = read(HERE / "layers.tsv", "\t")
  res = HERE / "results"
  sweep = {int(r["op"]): r for r in read(res / f"{a.base}.csv")
           if r["rows"] == "1" and r["status"] == "ok"}
  qins = {int(r["op"]): int(r["invoke_insns"])
          for r in read(res / f"{a.base}-qemu-insn.csv") if r["rows"] == "1"}
  rep = {r["config"]: int(r["op"]) for r in layers if r["rep"] == "1"}
  for cfg, op in rep.items():
    if op not in sweep or op not in qins:
      sys.exit(f"vector_estimate: missing measured row for op {op} ({cfg})")

  ref_total = 0.0
  cfg_ref, cfg_var = {}, {n: {} for n in names}
  for r in layers:
    op = rep[r["config"]]
    m = sweep[op]
    scale = int(r["work"]) / int(m["work"])
    ref_cyc = int(m["invoke_cycles"]) * scale
    ref_ins = qins[op] * scale
    ref_total += ref_cyc
    cfg_ref[r["config"]] = cfg_ref.get(r["config"], 0) + ref_cyc
    for n in names:
      c = op_cycles(scen[n], split, r["kind"], int(r["work"]), count(r["out_shape"]),
                    count(r["in_shape"]), ref_cyc, ref_ins)
      cfg_var[n][r["config"]] = cfg_var[n].get(r["config"], 0) + c

  print(f"reference total (measured, topology-scaled): {ref_total:.6g} cycles\n")
  print(f"{'scenario':<22} {'cycles':>14} {'speedup':>8}")
  for n in names:
    t = sum(cfg_var[n].values())
    print(f"{n:<22} {t:>14.6g} {ref_total / t:>7.2f}x")
  if a.per_config:
    for n in names:
      print(f"\n[{n}] {'config':<40} {'ref cycles':>14} {'cycles':>14} {'x':>7}")
      for cfg, rc in sorted(cfg_ref.items(), key=lambda kv: -kv[1]):
        v = cfg_var[n][cfg]
        print(f"     {cfg:<40} {rc:>14.6g} {v:>14.6g} {rc / v:>6.2f}x")
  return 0


if __name__ == "__main__":
  sys.exit(main())
