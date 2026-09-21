#!/usr/bin/env python3
"""Run the saved .tflite on all five JPEGs; write manifest and expected UART."""

import json
import sys
from pathlib import Path

from preprocess import jpeg_to_bytes

HERE = Path(__file__).resolve().parent
TFLITE = HERE / "resnet50_int8.tflite"
ORDER = HERE / "inputs" / "order.txt"
SPEC_PATH = HERE / "inputs" / "preprocess_spec.json"
MANIFEST = HERE / "inputs" / "manifest.tsv"
LABELS_TXT = HERE / "imagenet_labels.txt"
EXPECTED = HERE / "expected"


def interpreter_mod():
  try:
    from tflite_runtime.interpreter import Interpreter
    return Interpreter
  except ImportError:
    pass
  try:
    from ai_edge_litert.interpreter import Interpreter
    return Interpreter
  except ImportError:
    pass
  try:
    from tensorflow.lite import Interpreter
    return Interpreter
  except ImportError:
    sys.exit(
        "resnet50: install tflite_runtime, ai-edge-litert, or tensorflow for host_precheck")


def labels():
  if not LABELS_TXT.is_file():
    return ["?"]
  return [ln.strip() for ln in LABELS_TXT.read_text().splitlines() if ln.strip()]


def input_names():
  names = []
  for line in ORDER.read_text().splitlines():
    n = line.strip()
    if n and not n.startswith("#"):
      names.append(n)
  return names


def spec_from_details(d):
  shape = list(d["shape"])
  h, w = 224, 224
  if len(shape) == 4:
    h, w = int(shape[1]), int(shape[2])
  dtype = str(d["dtype"])
  if "uint8" in dtype:
    dt = "uint8"
  elif "int8" in dtype:
    dt = "int8"
  else:
    dt = "float32"
  q = d.get("quantization", (0.0, 0))
  scale, zp = float(q[0] or 0.0), int(q[1] or 0)
  spec = {
      "height": h,
      "width": w,
      "dtype": dt,
      "scale": scale if scale else 1.0,
      "zero_point": zp,
      "mean_rgb": [0.0, 0.0, 0.0],
      "std_rgb": [1.0, 1.0, 1.0],
      "rgb_to_bgr": False,
      "scale_to_01": dt == "float32",
  }
  return spec


def top1(output, labs, offset):
  import numpy as np
  flat = np.array(output).reshape(-1)
  idx = int(flat.argmax())
  lab_i = idx + offset
  lab = labs[lab_i] if lab_i < len(labs) else "?"
  return idx, lab, float(flat[idx])


def main():
  if not TFLITE.is_file():
    sys.exit(f"resnet50: missing {TFLITE}; run ./fetch.sh")
  Interpreter = interpreter_mod()
  labs = labels()
  interp = Interpreter(model_path=str(TFLITE))
  interp.allocate_tensors()
  din = interp.get_input_details()[0]
  dout = interp.get_output_details()[0]
  spec = spec_from_details(din)
  n_out = int(list(dout["shape"])[-1])
  n_lab = len(labs)
  offset = 0
  if n_out == 1000 and n_lab == 1001:
    offset = 1
  spec["label_offset"] = offset
  SPEC_PATH.write_text(json.dumps(spec, indent=2) + "\n")
  EXPECTED.mkdir(exist_ok=True)
  rows = ["name\tid\tlabel"]
  for name in input_names():
    jpeg = HERE / "inputs" / f"{name}.jpg"
    if not jpeg.is_file():
      sys.exit(f"resnet50: missing {jpeg}")
    raw = jpeg_to_bytes(jpeg, spec)
    import numpy as np
    arr = np.frombuffer(raw, dtype=np.uint8)
    if spec["dtype"] == "float32":
      arr = np.frombuffer(raw, dtype="<f4")
    elif spec["dtype"] == "int8":
      arr = np.frombuffer(raw, dtype=np.int8)
    arr = arr.reshape(din["shape"])
    interp.set_tensor(din["index"], arr)
    interp.invoke()
    out = interp.get_tensor(dout["index"])
    idx, lab, score = top1(out, labs, offset)
    rows.append(f"{name}\t{idx}\t{lab}")
    (EXPECTED / f"{name}.txt").write_text(
        f"invoke: ok\ntop1: {idx} {lab}\n")
    print(f"{name}: {idx} {lab} {score}")
  MANIFEST.write_text("\n".join(rows) + "\n")
  print(f"wrote {MANIFEST}")


if __name__ == "__main__":
  main()
