#!/usr/bin/env python3
"""Headless qemu-ajit run: match expected_uart.txt against -kernel ELF stdout."""

import os
import signal
import subprocess
import sys

EXPECTED_UART_FILE = "expected_uart.txt"
DEFAULT_TIMEOUT_SEC = 60
DEFAULT_ELF = "baremetal_qemu/main.elf"


def _needles(path):
  if not os.path.isfile(path):
    print(f"tflite: ERROR: missing {path}", file=sys.stderr)
    sys.exit(1)
  lines = []
  with open(path) as f:
    for raw in f:
      line = raw.strip()
      if not line or line.startswith("#"):
        continue
      lines.append(line)
  if not lines:
    print(f"tflite: ERROR: {path} has no expected substrings", file=sys.stderr)
    sys.exit(1)
  return lines


def _kill(proc):
  if proc.poll() is not None:
    return
  proc.terminate()
  try:
    proc.wait(timeout=3)
  except subprocess.TimeoutExpired:
    proc.kill()
    proc.wait()


def main():
  project_dir = os.getcwd()
  timeout_sec = int(os.environ.get("TFLITE_QEMU_TIMEOUT", DEFAULT_TIMEOUT_SEC))
  elf_rel = os.environ.get("TFLITE_QEMU_ELF", DEFAULT_ELF)
  expected_path = os.path.join(project_dir, EXPECTED_UART_FILE)
  elf_path = os.path.join(project_dir, elf_rel)
  needles = _needles(expected_path)
  if not os.path.isfile(elf_path):
    print(f"tflite: ERROR: missing {elf_path}", file=sys.stderr)
    sys.exit(1)

  qemu = os.environ.get("QEMU_SYSTEM_SPARC", "qemu-system-sparc")
  mem_mib = os.environ.get("TFLITE_QEMU_MEM", "128")
  cmd = [
      qemu,
      "-M", "ajit1_generic",
      "-cpu", "AJIT1",
      "-smp", "1",
      "-m", f"{mem_mib}M",
      "-display", "none",
      "-serial", "stdio",
      "-monitor", "none",
      "-nographic",
      "-kernel", elf_path,
  ]
  print("tflite: qemu:", " ".join(cmd))
  print(f"tflite: timeout {timeout_sec}s; expect {needles}")

  try:
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
  except FileNotFoundError:
    print("tflite: ERROR: qemu-system-sparc not on PATH", file=sys.stderr)
    sys.exit(1)

  buf = ""

  def _on_alarm(_s, _f):
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
        if all(n in buf for n in needles):
          _kill(proc)
          print("tflite: qemu UART match; stopping qemu.")
          sys.exit(0)
      elif proc.poll() is not None:
        buf += proc.stdout.read() or ""
        break
  except TimeoutError:
    _kill(proc)
    print(f"tflite: ERROR: qemu timeout ({timeout_sec}s)", file=sys.stderr)
    sys.exit(1)
  finally:
    signal.alarm(0)
    signal.signal(signal.SIGALRM, old)

  if all(n in buf for n in needles):
    print("tflite: qemu UART match.")
    sys.exit(0)
  print("tflite: ERROR: qemu exited without expected UART text", file=sys.stderr)
  sys.exit(1)


if __name__ == "__main__":
  main()
