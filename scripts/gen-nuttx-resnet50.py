#!/usr/bin/env python3
"""Objcopy the ResNet-50 int8 model and write its label table for NuttX.

Input images are files on the /tflite ROMFS, built by gen-nuttx-tflite-fs.py.

Generated files stay out of git. A missing source path exits non-zero and
prints that path.
"""

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "os/rtos/cortos2/examples/tflite/resnet50"


def die(path: Path) -> None:
    sys.stderr.write(f"resnet50: missing {path}\n")
    sys.exit(1)


def need(path: Path) -> Path:
    if not path.is_file():
        die(path)
    return path


def write_labels(out: Path, labels_txt: Path, offset: int) -> None:
    labels = []
    for line in labels_txt.read_text().splitlines():
        text = line.strip()
        if text:
            labels.append(text.replace("\\", "\\\\").replace('"', '\\"'))
    if offset:
        labels = labels[offset:]
    if not labels:
        die(labels_txt)
    body = ",\n".join(f'  "{text}"' for text in labels)
    (out / "labels.h").write_text(
        "#pragma once\n"
        f"constexpr int kLabelCount = {len(labels)};\n"
        "extern const char *const kLabels[];\n"
    )
    (out / "labels.cc").write_text(
        '#include "labels.h"\n'
        f"const char *const kLabels[{len(labels)}] = {{\n{body}\n}};\n"
    )


def objcopy_model(model: Path, out: Path) -> None:
    blob = out / "model.tflite"
    shutil.copyfile(model, blob)
    subprocess.check_call(
        [
            "sparc-linux-objcopy",
            "-I",
            "binary",
            "-O",
            "elf32-sparc",
            "-B",
            "sparc",
            "--rename-section",
            ".data=.rodata,alloc,load,readonly,data,contents",
            "model.tflite",
            "model.o",
        ],
        cwd=out,
    )
    subprocess.check_call(
        ["sparc-linux-ar", "rcs", "libmodelblob.a", "model.o"], cwd=out
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    parser.add_argument("--model", default=None)
    args = parser.parse_args()

    model = Path(args.model) if args.model else SRC / "resnet50_int8.tflite"
    if not model.is_file():
        die(model)

    sys.path.insert(0, str(SRC))
    from preprocess import load_spec

    spec_path = need(SRC / "inputs" / "preprocess_spec.json")
    labels_path = need(SRC / "imagenet_labels.txt")
    spec = load_spec(spec_path)

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    write_labels(out, labels_path, int(spec.get("label_offset", 0)))
    objcopy_model(model, out)
    print(f"resnet50: model {model}")


if __name__ == "__main__":
    main()
