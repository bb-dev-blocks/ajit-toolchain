#!/usr/bin/env python3
"""Exact instruction counts of one Invoke call on qemu-ajit.

Runs the ELF twice under qemu with libinsn + libstoptrigger: once stopping at
the `call <Invoke>` instruction, once at its return address (call + 8). The
difference is the instructions executed inside Invoke.

  qemu_insn.py model                 full ResNet-50 (../resnet50 qemu build)
  qemu_insn.py layers [op[:rows]...] harness layers (default: every
                                     representative op, ROWS=1); builds each
                                     with TARGET=qemu → results/<variant>-qemu-insn.csv
"""
import argparse
import csv
import os
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
QEMU_BUILD = Path(os.environ.get("AJIT_HOME", HERE.parents[5])) / "build/qemu-ajit-v1.0"
PLUGINS = (QEMU_BUILD / "tests/tcg/plugins/libinsn.so",
           QEMU_BUILD / "contrib/plugins/libstoptrigger.so")
QEMU = ["qemu-system-sparc", "-M", "ajit1_generic", "-cpu", "AJIT1", "-smp", "1",
        "-m", "128M", "-display", "none", "-serial", "stdio", "-monitor", "none",
        "-nographic", "-d", "plugin"]


def call_site(elf: Path, caller: str, callee: str) -> int:
  dis = subprocess.run(["sparc-linux-objdump", "-d", "--no-show-raw-insn",
                        f"--disassemble={caller}", str(elf)],
                       check=True, capture_output=True, text=True).stdout
  hits = re.findall(rf"^\s*([0-9a-f]+):\s+call\s+\S+ <{callee}>", dis, re.M)
  if len(hits) != 1:
    sys.exit(f"qemu_insn: {elf}: {len(hits)} calls to {callee} in {caller}")
  return int(hits[0], 16)


def insns_until(elf: Path, addr: int, timeout: int) -> int:
  cmd = QEMU + ["-plugin", str(PLUGINS[0]),
                "-plugin", f"{PLUGINS[1]},addr={addr:#x}", "-kernel", str(elf)]
  out = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                       text=True, timeout=timeout,
                       stdin=subprocess.DEVNULL).stdout
  if f"{addr:#x} reached" not in out:
    sys.exit(f"qemu_insn: {elf}: stop address {addr:#x} not reached")
  return int(re.search(r"total insns: (\d+)", out).group(1))


def invoke_insns(elf: Path, caller: str, callee: str, timeout: int) -> int:
  a = call_site(elf, caller, callee)
  with ThreadPoolExecutor(2) as ex:
    pre, post = ex.map(lambda x: insns_until(elf, x, timeout), (a, a + 8))
  return post - pre


def reps():
  with open(HERE / "layers.tsv") as f:
    return [r["op"] for r in csv.DictReader(f, delimiter="\t") if r["rep"] == "1"]


def layer_job(variant: str, entry: str, timeout: int) -> dict:
  op, _, rows = entry.partition(":")
  rows = rows or "1"
  work = HERE / "work" / variant / "qemu" / f"L{op}_R{rows}"
  env = dict(os.environ, LAYER=op, ROWS=rows, VARIANT=variant, TARGET="qemu",
             WORK=str(work))
  work.mkdir(parents=True, exist_ok=True)
  with open(work / "build.log", "w") as log:
    subprocess.run([str(HERE / "build.sh")], env=env, stdout=log,
                   stderr=subprocess.STDOUT, check=True)
  n = invoke_insns(work / "cortos_build_qemu" / "main.elf", "main",
                   r"_ZN\w*11LayerRunner6InvokeEv", timeout)
  return dict(op=op, rows=rows, invoke_insns=n)


def main() -> int:
  ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
  ap.add_argument("what", choices=["model", "layers"])
  ap.add_argument("entries", nargs="*")
  ap.add_argument("-j", type=int, default=4)
  ap.add_argument("--timeout", type=int, default=7200)
  a = ap.parse_args()
  if a.what == "model":
    elf = HERE.parent / "resnet50" / "cortos_build_qemu" / "main.elf"
    n = invoke_insns(elf, "main", r"_ZN6tflite16MicroInterpreter6InvokeEv",
                     a.timeout)
    out = HERE / "results" / "qemu-model-insn.txt"
    out.parent.mkdir(exist_ok=True)
    out.write_text(f"invoke_insns\t{n}\n")
    print(f"resnet50 invoke instructions: {n} → {out.relative_to(HERE)}")
    return 0
  variant = os.environ.get("VARIANT", "reference")
  with ThreadPoolExecutor(a.j) as ex:
    rows = list(ex.map(lambda e: layer_job(variant, e, a.timeout),
                       a.entries or reps()))
  out = HERE / "results" / f"{variant}-qemu-insn.csv"
  out.parent.mkdir(exist_ok=True)
  with open(out, "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=["op", "rows", "invoke_insns"])
    w.writeheader()
    w.writerows(rows)
  for r in rows:
    print(f"L{r['op']:<3} R{r['rows']} {r['invoke_insns']}")
  print(f"qemu_insn: {len(rows)} rows → {out.relative_to(HERE)}")
  return 0


if __name__ == "__main__":
  sys.exit(main())
