#!/usr/bin/env python3
"""List every op of the ResNet-50 int8 model with its shapes and work.

Writes layers.tsv: one row per op index with kind, shapes, stride, padding,
MACs (CONV_2D, FULLY_CONNECTED) or output elements (other ops), the
configuration id it shares with identical ops, and whether it is the
representative op that the C-model sweep measures for that configuration.
"""

import argparse
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
AJIT_HOME = HERE.parents[5]
sys.path.insert(0, str(AJIT_HOME / "tflite-micro/tensorflow/lite/python"))
import schema_py_generated as S  # noqa: E402

MODEL = HERE.parent / "resnet50" / "resnet50_int8.tflite"
COLUMNS = ("op", "kind", "config", "rep", "stage", "in_shape", "filter_shape",
           "out_shape", "stride", "padding", "macs", "exec_macs", "out_elems",
           "work", "work_unit")

_OP_NAMES = {v: k for k, v in vars(S.BuiltinOperator).items()
             if not k.startswith("_")}
_PADDING = {v: k for k, v in vars(S.Padding).items() if not k.startswith("_")}


def _shape(g, idx):
  if idx < 0:
    return ()
  t = g.Tensors(idx)
  return tuple(int(d) for d in t.ShapeAsNumpy()) if t.ShapeLength() else ()


def _fmt(shape):
  return "x".join(str(d) for d in shape) if shape else "-"


def _stage(out_shape):
  # ResNet-50 v1 stages by output spatial size.
  if len(out_shape) != 4:
    return "head"
  # PAD before a stride-2 conv adds one row (57, 29, 15) and belongs to the
  # stage that conv produces.
  return {112: "stem", 113: "stem", 56: "conv2", 57: "conv3", 28: "conv3",
          29: "conv4", 14: "conv4", 15: "conv5", 7: "conv5",
          1: "head"}.get(out_shape[1], "input")


def _taps_in_bounds(out_n, in_n, k, s, same):
  """Sum over output positions of filter taps that land inside the input.

  TFLM's reference conv skips taps that fall in SAME padding, so a padded
  layer executes fewer MACs than out x k x cin x cout.
  """
  pad = max((out_n - 1) * s + k - in_n, 0) // 2 if same else 0
  return sum(sum(1 for t in range(k) if 0 <= o * s - pad + t < in_n)
             for o in range(out_n))


def model_graph(model_path):
  m = S.Model.GetRootAsModel(model_path.read_bytes(), 0)
  return m, m.Subgraphs(0)


def op_kind(m, op):
  code = m.OperatorCodes(op.OpcodeIndex())
  return _OP_NAMES[max(code.BuiltinCode(), code.DeprecatedBuiltinCode())]


def inventory(model_path):
  m, g = model_graph(model_path)
  rows = []
  for i in range(g.OperatorsLength()):
    op = g.Operators(i)
    kind = op_kind(m, op)
    ins, outs = op.InputsAsNumpy(), op.OutputsAsNumpy()
    x, o = _shape(g, ins[0]), _shape(g, outs[0])
    w = _shape(g, ins[1]) if kind in ("CONV_2D", "FULLY_CONNECTED") else ()
    stride, padding, macs, exec_macs = "-", "-", 0, 0
    if kind == "CONV_2D":
      opt = S.Conv2DOptions()
      t = op.BuiltinOptions()
      opt.Init(t.Bytes, t.Pos)
      stride = f"{opt.StrideH()}x{opt.StrideW()}"
      padding = _PADDING[opt.Padding()]
      macs = o[1] * o[2] * o[3] * w[1] * w[2] * w[3]
      same = padding == "SAME"
      exec_macs = (_taps_in_bounds(o[1], x[1], w[1], opt.StrideH(), same)
                   * _taps_in_bounds(o[2], x[2], w[2], opt.StrideW(), same)
                   * w[3] * o[3])
      config = f"conv{w[1]}x{w[2]}_s{opt.StrideH()}_{x[3]}to{o[3]}_in{x[1]}"
    elif kind == "FULLY_CONNECTED":
      macs = exec_macs = w[0] * w[1]
      config = f"fc_{w[1]}to{w[0]}"
    else:
      config = f"{kind.lower()}_{_fmt(x)}_to_{_fmt(o)}"
    out_elems = 1
    for d in o:
      out_elems *= d
    in_elems = 1
    for d in x:
      in_elems *= d
    if exec_macs:
      work, unit = exec_macs, "mac"
    elif kind == "MEAN":
      work, unit = in_elems, "in_elem"
    else:
      work, unit = out_elems, "out_elem"
    rows.append(dict(op=i, kind=kind, config=config, rep=0, stage=_stage(o),
                     in_shape=_fmt(x), filter_shape=_fmt(w), out_shape=_fmt(o),
                     stride=stride, padding=padding, macs=macs,
                     exec_macs=exec_macs, out_elems=out_elems, work=work,
                     work_unit=unit))
  seen = set()
  for r in rows:
    if r["config"] not in seen:
      r["rep"] = 1
      seen.add(r["config"])
  return rows


def main():
  ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
  ap.add_argument("--model", type=Path, default=MODEL)
  ap.add_argument("--out", type=Path, default=HERE / "layers.tsv")
  args = ap.parse_args()
  rows = inventory(args.model)
  with args.out.open("w") as f:
    f.write("\t".join(COLUMNS) + "\n")
    for r in rows:
      f.write("\t".join(str(r[c]) for c in COLUMNS) + "\n")
  convs = [r for r in rows if r["kind"] == "CONV_2D"]
  print(f"ops={len(rows)} macs={sum(r['macs'] for r in rows)} "
        f"conv_ops={len(convs)} conv_configs={len({r['config'] for r in convs})} "
        f"configs={sum(r['rep'] for r in rows)} -> {args.out.name}")


if __name__ == "__main__":
  main()
