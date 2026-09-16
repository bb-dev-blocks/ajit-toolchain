#!/usr/bin/env python3
"""Shared JPEG → model-input bytes for host_precheck and generate_runtime."""

import json
from pathlib import Path

from PIL import Image


def load_spec(path: Path) -> dict:
  if path.is_file():
    return json.loads(path.read_text())
  return {
      "height": 224,
      "width": 224,
      "dtype": "uint8",
      "scale": 1.0,
      "zero_point": 0,
      "mean_rgb": [0.0, 0.0, 0.0],
      "std_rgb": [1.0, 1.0, 1.0],
      "rgb_to_bgr": False,
      "scale_to_01": False,
  }


def jpeg_to_bytes(jpeg: Path, spec: dict) -> bytes:
  h = int(spec.get("height", 224))
  w = int(spec.get("width", 224))
  img = Image.open(jpeg).convert("RGB").resize((w, h), Image.BILINEAR)
  pixels = list(img.getdata())
  mean = spec.get("mean_rgb", [0.0, 0.0, 0.0])
  std = spec.get("std_rgb", [1.0, 1.0, 1.0])
  rgb_to_bgr = bool(spec.get("rgb_to_bgr", False))
  scale_to_01 = bool(spec.get("scale_to_01", False))
  dtype = spec.get("dtype", "uint8")
  zp = int(spec.get("zero_point", 0))
  qscale = float(spec.get("scale", 1.0) or 1.0)
  out = bytearray()
  for r, g, b in pixels:
    vals = [float(r), float(g), float(b)]
    if rgb_to_bgr:
      vals = [vals[2], vals[1], vals[0]]
    if scale_to_01:
      vals = [v / 255.0 for v in vals]
    vals = [(vals[i] - mean[i]) / std[i] for i in range(3)]
    for v in vals:
      if dtype == "float32":
        import struct
        out.extend(struct.pack("<f", v))
      elif dtype == "int8":
        q = int(round(v / qscale + zp))
        q = max(-128, min(127, q))
        out.append(q & 0xFF)
      else:
        # uint8 image tensors already store 0-255 RGB. Do not divide by the
        # interpreter scale (often 1/255); that saturates every pixel.
        q = int(round(v))
        q = max(0, min(255, q))
        out.append(q)
  return bytes(out)
