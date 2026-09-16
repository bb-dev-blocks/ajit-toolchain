#!/usr/bin/env python3
"""Build-time: selected JPEG → C array; tflite → libmodelblob.a; labels.cc."""

import os
import shutil
import subprocess
import sys
from pathlib import Path

from preprocess import jpeg_to_bytes, load_spec

HERE = Path(__file__).resolve().parent
GEN = HERE / "gen"
TFLITE = HERE / "resnet50_int8.tflite"
ORDER = HERE / "inputs" / "order.txt"
SPEC = HERE / "inputs" / "preprocess_spec.json"
LABELS_TXT = HERE / "imagenet_labels.txt"


def default_input_name() -> str:
  for line in ORDER.read_text().splitlines():
    name = line.strip()
    if name and not name.startswith("#"):
      return name
  sys.exit("resnet50: inputs/order.txt is empty")


def write_cc_array(cc: Path, hdr: Path, name: str, data: bytes, ctype: str):
  hexes = ",".join(hex(b) for b in data)
  hdr.write_text(
      f"#pragma once\n#include <cstdint>\n"
      f"constexpr unsigned int {name}_size = {len(data)};\n"
      f"extern const {ctype} {name}[];\n")
  cc.write_text(
      f'#include "{hdr.name}"\n'
      f"alignas(16) const {ctype} {name}[] = {{{hexes}}};\n")


def write_labels_cc(txt: Path, offset: int):
  labels = []
  if txt.is_file():
    for line in txt.read_text().splitlines():
      s = line.strip()
      if s:
        labels.append(s.replace("\\", "\\\\").replace('"', '\\"'))
  if offset:
    labels = labels[offset:]
  if not labels:
    labels = ["unknown"]
  body = ",\n".join(f'  "{s}"' for s in labels)
  (GEN / "labels.h").write_text(
      "#pragma once\n"
      f"constexpr int kLabelCount = {len(labels)};\n"
      "extern const char* const kLabels[];\n")
  (GEN / "labels.cc").write_text(
      '#include "labels.h"\n'
      f"const char* const kLabels[{len(labels)}] = {{\n{body}\n}};\n")


def objcopy_model():
  if not TFLITE.is_file():
    sys.exit(f"resnet50: missing {TFLITE}; run ./fetch.sh")
  GEN.mkdir(exist_ok=True)
  blob = GEN / "model.tflite"
  shutil.copyfile(TFLITE, blob)
  obj = GEN / "model.o"
  lib = GEN / "libmodelblob.a"
  cmd = [
      "sparc-linux-objcopy", "-I", "binary", "-O", "elf32-sparc", "-B", "sparc",
      "--rename-section",
      ".data=.rodata,alloc,load,readonly,data,contents",
      str(blob.name), str(obj.name),
  ]
  subprocess.check_call(cmd, cwd=GEN)
  subprocess.check_call(["sparc-linux-ar", "rcs", str(lib.name), str(obj.name)],
                        cwd=GEN)


def copy_expected(name: str):
  src = HERE / "expected" / f"{name}.txt"
  if not src.is_file():
    src = HERE / "expected" / "_stub.txt"
  shutil.copyfile(src, HERE / "expected_uart.txt")


def main():
  GEN.mkdir(exist_ok=True)
  name = os.environ.get("INPUT") or ""
  if not name:
    name = default_input_name()
  jpeg = HERE / "inputs" / f"{name}.jpg"
  if not jpeg.is_file():
    sys.exit(f"resnet50: missing {jpeg}")
  spec = load_spec(SPEC)
  data = jpeg_to_bytes(jpeg, spec)
  write_cc_array(GEN / "input_data.cc", GEN / "input_data.h",
                 "g_input_image_data", data, "uint8_t")
  write_labels_cc(LABELS_TXT, int(spec.get("label_offset", 0)))
  objcopy_model()
  copy_expected(name)
  print(f"resnet50: INPUT={name} input_bytes={len(data)}")


if __name__ == "__main__":
  main()
