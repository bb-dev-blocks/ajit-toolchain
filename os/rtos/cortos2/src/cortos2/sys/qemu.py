#!/usr/bin/env python3
"""Headless qemu-ajit run helper for cortos2 examples."""

import os
import signal
import subprocess
import sys
from typing import List, Tuple

import yaml

from cortos2.common import consts

EXPECTED_UART_FILE = "expected_uart.txt"
DEFAULT_TIMEOUT_SEC = 30


def _required_substrings(path: str) -> List[str]:
  if not os.path.isfile(path):
    print(f"CoRTOS: ERROR: missing {path}", file=sys.stderr)
    sys.exit(1)
  lines: List[str] = []
  with open(path) as f:
    for raw in f:
      line = raw.strip()
      if not line or line.startswith("#"):
        continue
      lines.append(line)
  if not lines:
    print(f"CoRTOS: ERROR: {path} has no expected substrings", file=sys.stderr)
    sys.exit(1)
  return lines


def _kill_qemu(proc: subprocess.Popen) -> None:
  if proc.poll() is not None:
    return
  proc.terminate()
  try:
    proc.wait(timeout=3)
  except subprocess.TimeoutExpired:
    proc.kill()
    proc.wait()


def _smp_and_mem_mib(project_dir: str) -> Tuple[int, int]:
  """Hardware.Processor thread count → qemu -smp. -m at least 128MiB."""
  path = os.path.join(project_dir, consts.CONFIG_FILE_DEFAULT_NAME)
  cores, tpc = 1, 1
  if os.path.isfile(path):
    with open(path) as f:
      data = yaml.safe_load(f) or {}
    proc = (data.get("Hardware") or {}).get("Processor") or {}
    cores = int(proc.get("Cores") or 1)
    tpc = int(proc.get("ThreadsPerCore") or 1)
  smp = max(1, min(cores * tpc, 4))
  return smp, 128


def run_qemu(
    project_dir: str,
    timeout_sec: int = DEFAULT_TIMEOUT_SEC,
) -> None:
  """Run cortos_build_qemu/main.elf; exit 0 iff expected UART text appears."""
  expected_path = os.path.join(project_dir, EXPECTED_UART_FILE)
  needles = _required_substrings(expected_path)
  elf_path = os.path.join(
      project_dir, consts.CORTOS_BUILD_QEMU_DIR_NAME, consts.ELF_FILE_NAME)
  if not os.path.isfile(elf_path):
    print(f"CoRTOS: ERROR: missing {elf_path} (run build_qemu.sh first)",
          file=sys.stderr)
    sys.exit(1)

  smp, mem_mib = _smp_and_mem_mib(project_dir)
  serial_in_path = os.path.join(project_dir, "serial_in.txt")
  serial_in = ""
  if os.path.isfile(serial_in_path):
    with open(serial_in_path) as f:
      serial_in = f.read()
  qemu = os.environ.get("QEMU_SYSTEM_SPARC", "qemu-system-sparc")
  cmd = [
      qemu,
      "-M", "ajit1_generic",
      "-cpu", "AJIT1",
      "-smp", str(smp),
      "-m", f"{mem_mib}M",
      "-display", "none",
      "-serial", "stdio",
      "-monitor", "none",
      "-nographic",
      "-kernel", elf_path,
  ]
  print("CoRTOS: qemu:", " ".join(cmd))
  print(f"CoRTOS: timeout {timeout_sec}s; expect {needles}")

  try:
    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE if serial_in else subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
  except FileNotFoundError:
    print("CoRTOS: ERROR: qemu-system-sparc not on PATH (setup_qemu.sh, ajit_env)",
          file=sys.stderr)
    sys.exit(1)

  assert proc.stdout is not None
  buf = ""

  def _on_alarm(_signum, _frame):
    raise TimeoutError()

  old = signal.signal(signal.SIGALRM, _on_alarm)
  signal.alarm(timeout_sec)
  try:
    while True:
      line = proc.stdout.readline()
      if line:
        sys.stdout.write(line)
        sys.stdout.flush()
        buf += line
        # Guest has printed, so UART RX interrupt can already be enabled.
        if serial_in and proc.stdin is not None:
          proc.stdin.write(serial_in)
          proc.stdin.flush()
          serial_in = ""
        if all(n in buf for n in needles):
          _kill_qemu(proc)
          print("CoRTOS: qemu UART match; stopping qemu.")
          sys.exit(0)
      elif proc.poll() is not None:
        rest = proc.stdout.read() or ""
        buf += rest
        break
  except TimeoutError:
    _kill_qemu(proc)
    print(f"CoRTOS: ERROR: qemu timeout ({timeout_sec}s)", file=sys.stderr)
    sys.exit(1)
  finally:
    signal.alarm(0)
    signal.signal(signal.SIGALRM, old)

  if all(n in buf for n in needles):
    print("CoRTOS: qemu UART match.")
    sys.exit(0)
  print("CoRTOS: ERROR: qemu exited without expected UART text", file=sys.stderr)
  sys.exit(1)
