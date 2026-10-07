#!/usr/bin/env python3
"""Turn an ajit_C_system_model run log into a metric table.

The log must hold both stdout (app UART) and stderr (halt statistics), e.g.
`./run.sh > run.log 2>&1`. Exits non-zero when the halt statistics block is
missing or when a non-comment line of the optional expected file does not
appear in the log.

Cycle figures are the C-model's analytic estimate (instructions plus cache,
TLB, trap and mispredict penalties), not silicon cycles.
"""

import argparse
import csv
import re
import sys
from pathlib import Path

# Single-value stats printed once per run (core 0, thread 0 is the first block).
_PATTERNS = {
    "instructions": r"number-of-instructions-executed = (\d+)",
    "traps": r"number-of-traps\s+= (\d+)",
    "cti": r"number-of-cti\s+= (\d+)",
    "cti_mispredicts": r"number-of-cti\s+= \d+, mispredicts=(\d+)",
    "cycles": r"cycle-count estimate = (\d+)",
    "ras_mispredicts": r"RAS: push-count=\d+, pop-count=\d+, mispredicts=(\d+)",
    "mmu_bypass_accesses": r"Accesses with Mmu bypassed or disabled\s+= (\d+)",
    "mmu_translated": r"Mmu_translated_accesses = (\d+)",
    "mmu_tlb_hits": r"Mmu_TLB_hits\s+= (\d+)",
    "wall_s": r"Total time taken by testbench: (\d+) secs",
}

_CACHE_FIELDS = ("accesses", "hits", "misses", "read_hits", "read_misses",
                 "write_hits", "write_misses")

# App lines of the form `key: value` that the layer harness prints.
_APP_KEYS = ("layer", "cycles", "checksum")

FIELDS = (
    ["instructions", "cycles", "cpi", "traps", "cti", "cti_mispredicts",
     "ras_mispredicts", "mmu_bypass_accesses", "mmu_translated",
     "mmu_tlb_hits", "tlb_misses"]
    + [f"icache_{f}" for f in _CACHE_FIELDS[:3]]
    + [f"dcache_{f}" for f in _CACHE_FIELDS]
    + ["wall_s", "instr_per_s"]
    + [f"app_{k}" for k in _APP_KEYS]
)


def _cache_block(text: str, name: str) -> dict:
  m = re.search(rf"Statistics for {name} core-id=0\n((?:\s+number-of-[^\n]*\n?)+)",
                text)
  out = {}
  if not m:
    return out
  for key, val in re.findall(r"number-of-([a-z_]+)=(\d+)", m.group(1)):
    out[f"{name.lower()}_{key}"] = int(val)
  return out


def parse(text: str) -> dict:
  if "Statistics for Thread" not in text:
    raise ValueError("no C-model halt statistics in log")
  row = {}
  for key, pat in _PATTERNS.items():
    m = re.search(pat, text)
    if m:
      row[key] = int(m.group(1))
  row.update(_cache_block(text, "ICACHE"))
  row.update(_cache_block(text, "DCACHE"))
  if row.get("instructions"):
    row["cpi"] = round(row["cycles"] / row["instructions"], 4)
    if row.get("wall_s"):
      row["instr_per_s"] = row["instructions"] // max(row["wall_s"], 1)
  if "mmu_translated" in row and "mmu_tlb_hits" in row:
    row["tlb_misses"] = row["mmu_translated"] - row["mmu_tlb_hits"]
  for key in _APP_KEYS:
    m = re.search(rf"^{key}: (.*)$", text, re.MULTILINE)
    if m:
      row[f"app_{key}"] = m.group(1).strip()
  return row


def missing_expected(text: str, expected: Path) -> list:
  lines = [l.strip() for l in expected.read_text().splitlines()]
  return [l for l in lines if l and not l.startswith("#") and l not in text]


def main() -> int:
  ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
  ap.add_argument("log", type=Path)
  ap.add_argument("expected", type=Path, nargs="?",
                  help="expected_uart.txt; every non-comment line must appear")
  ap.add_argument("--csv", action="store_true",
                  help="print one CSV header + row instead of a table")
  args = ap.parse_args()

  text = args.log.read_text(errors="replace")
  try:
    row = parse(text)
  except ValueError as e:
    print(f"cmodel_metrics: {args.log}: {e}", file=sys.stderr)
    return 2

  if args.csv:
    w = csv.DictWriter(sys.stdout, fieldnames=FIELDS, extrasaction="ignore")
    w.writeheader()
    w.writerow(row)
  else:
    for key in FIELDS:
      if key in row:
        print(f"{key:22s} {row[key]}")

  if args.expected:
    missing = missing_expected(text, args.expected)
    for line in missing:
      print(f"cmodel_metrics: missing expected line: {line}", file=sys.stderr)
    if missing:
      return 1
  return 0


if __name__ == "__main__":
  sys.exit(main())
