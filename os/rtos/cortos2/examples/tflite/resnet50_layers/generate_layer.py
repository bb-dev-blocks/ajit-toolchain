#!/usr/bin/env python3
"""Build-time: one ResNet-50 op → gen/layer_params.h + gen/liblayerblob.a.

Reads op LAYER from the committed resnet50_int8.tflite, crops it to ROWS
output rows, and emits the tensor descriptions, quantization, builtin
options and work count the harness needs. Constant tensors (weights, bias,
paddings, axes) go into an objcopy'd blob so only this op's data is linked.

SAME convolutions become VALID on an input that already includes the padding
rows/columns, so every tap of the measured rows executes (interior-row cost).
"""

import argparse
import struct
import subprocess
import sys
from pathlib import Path

import inventory as inv

S = inv.S

# schema TensorType name → TfLiteType value (tensorflow/lite/core/c/c_api_types.h)
_TFLITE_TYPE = {"FLOAT32": 1, "INT32": 2, "UINT8": 3, "INT64": 4, "INT16": 7,
                "INT8": 9}
_TYPE_SIZE = {"FLOAT32": 4, "INT32": 4, "UINT8": 1, "INT64": 8, "INT16": 2,
              "INT8": 1}
_TENSOR_TYPE = {v: k for k, v in vars(S.TensorType).items()
                if not k.startswith("_")}
KINDS = ("CONV_2D", "FULLY_CONNECTED", "ADD", "SUB", "MUL", "PAD",
         "CONCATENATION", "QUANTIZE", "MAX_POOL_2D", "MEAN")

SRC_BLOB, SRC_FILL, SRC_OUTPUT, SRC_ABSENT = 0, 1, 2, 3


def _opts(op, cls):
  t = op.BuiltinOptions()
  if t is None:
    return None
  o = cls()
  o.Init(t.Bytes, t.Pos)
  return o


def _buffer(m, g, idx):
  b = m.Buffers(g.Tensors(idx).Buffer())
  return bytes(b.DataAsNumpy()) if b is not None and b.DataLength() else b""


def _window_in(out_n, k, s):
  return (out_n - 1) * s + k


def crop(kind, op, m, g, rows):
  """Return (input dims list, output dims, options dict) for the cropped op."""
  ins, outs = list(op.InputsAsNumpy()), list(op.OutputsAsNumpy())
  dims = [list(inv._shape(g, i)) if i >= 0 else [] for i in ins]
  out = list(inv._shape(g, outs[0]))
  opt = {}
  if kind == "CONV_2D":
    c = _opts(op, S.Conv2DOptions)
    w = dims[1]
    rows = min(rows, out[1])
    out[1] = rows
    dims[0][1] = _window_in(rows, w[1], c.StrideH())
    dims[0][2] = _window_in(out[2], w[2], c.StrideW())
    opt = dict(padding=2, stride_w=c.StrideW(), stride_h=c.StrideH(),
               dil_w=c.DilationWFactor(), dil_h=c.DilationHFactor(),
               activation=c.FusedActivationFunction())
  elif kind == "MAX_POOL_2D":
    p = _opts(op, S.Pool2DOptions)
    rows = min(rows, out[1])
    out[1] = rows
    dims[0][1] = _window_in(rows, p.FilterHeight(), p.StrideH())
    dims[0][2] = _window_in(out[2], p.FilterWidth(), p.StrideW())
    opt = dict(padding=2, stride_w=p.StrideW(), stride_h=p.StrideH(),
               filter_w=p.FilterWidth(), filter_h=p.FilterHeight(),
               activation=p.FusedActivationFunction())
  elif kind == "FULLY_CONNECTED":
    f = _opts(op, S.FullyConnectedOptions)
    rows = 1
    opt = dict(activation=f.FusedActivationFunction(),
               keep_num_dims=int(f.KeepNumDims()))
  elif kind in ("ADD", "SUB", "MUL", "QUANTIZE", "MEAN", "PAD"):
    if len(out) == 4 and kind != "MEAN":
      rows = min(rows, out[1])
    elif kind == "MEAN":
      rows = min(rows, dims[0][1])
    else:
      rows = 1
    for j, d in enumerate(dims):
      if len(d) == 4 and d[1] > 1 and not _buffer(m, g, ins[j]):
        d[1] = rows
    if kind == "PAD":
      pads = struct.unpack(f"<{len(_buffer(m, g, ins[1])) // 4}i",
                           _buffer(m, g, ins[1]))
      out[1] = rows + pads[2] + pads[3]
    elif len(out) == 4 and kind != "MEAN":
      out[1] = rows
    if kind in ("ADD", "SUB", "MUL"):
      cls = {"ADD": S.AddOptions, "SUB": S.SubOptions, "MUL": S.MulOptions}[kind]
      o = _opts(op, cls)
      opt = dict(activation=o.FusedActivationFunction() if o else 0)
    if kind == "MEAN":
      r = _opts(op, S.ReducerOptions)
      opt = dict(keep_dims=int(r.KeepDims()) if r else 0)
  elif kind == "CONCATENATION":
    c = _opts(op, S.ConcatenationOptions)
    axis = c.Axis() + len(out) if c.Axis() < 0 else c.Axis()
    rows = min(rows, out[1])
    for d in dims:
      if not (axis == 1 and d[1] == 1):
        d[1] = rows
    out[1] = sum(d[1] for d in dims) if axis == 1 else rows
    opt = dict(axis=axis, activation=c.FusedActivationFunction())
  else:
    sys.exit(f"generate_layer: unsupported op kind {kind}")
  return dims, out, opt, rows


def _quant(g, idx):
  q = g.Tensors(idx).Quantization()
  if q is None or q.ScaleLength() == 0:
    return [], [], 0
  return (list(q.ScaleAsNumpy()), [int(z) for z in q.ZeroPointAsNumpy()],
          q.QuantizedDimension())


def _count(d):
  n = 1
  for x in d:
    n *= x
  return n


def _work(kind, dims, out, opt):
  if kind == "CONV_2D":
    w = dims[1]
    return _count(out) * w[1] * w[2] * w[3], "mac"
  if kind == "FULLY_CONNECTED":
    return dims[1][0] * dims[1][1], "mac"
  if kind == "MEAN":
    return _count(dims[0]), "in_elem"
  return _count(out), "out_elem"


def generate(layer, rows, gen):
  m, g = inv.model_graph(inv.MODEL)
  if not 0 <= layer < g.OperatorsLength():
    sys.exit(f"generate_layer: LAYER {layer} outside 0..{g.OperatorsLength()-1}")
  op = g.Operators(layer)
  kind = inv.op_kind(m, op)
  if kind not in KINDS:
    sys.exit(f"generate_layer: op {layer} kind {kind} not supported")
  dims, out_dims, opt, rows = crop(kind, op, m, g, rows)
  ins, outs = list(op.InputsAsNumpy()), list(op.OutputsAsNumpy())

  blob = bytearray()
  scales, zps, descs = [], [], []
  act_bytes = 0
  for i, idx in enumerate(ins + outs[:1]):
    is_out = i == len(ins)
    if idx < 0:
      descs.append((0, [0], SRC_ABSENT, 0, 0, 0, 0, 0))
      continue
    t = g.Tensors(idx)
    tname = _TENSOR_TYPE[t.Type()]
    d = out_dims if is_out else dims[i]
    nbytes = _count(d) * _TYPE_SIZE[tname]
    data = b"" if is_out else _buffer(m, g, idx)
    if data:
      while len(blob) % 16:
        blob.append(0)
      src, off = SRC_BLOB, len(blob)
      # A cropped constant (e.g. a concat pad row block) keeps its leading rows.
      data = data[:nbytes]
      # .tflite constants are little-endian; the SPARC target is big-endian and
      # TFLM's allocator (bypassed here) normally byte-swaps them at load.
      size = _TYPE_SIZE[tname]
      if size > 1:
        data = b"".join(data[k:k + size][::-1]
                        for k in range(0, len(data), size))
      blob.extend(data)
    else:
      src, off = (SRC_OUTPUT if is_out else SRC_FILL), act_bytes
      act_bytes += (nbytes + 15) // 16 * 16
    sc, zp, qdim = _quant(g, idx)
    descs.append((_TFLITE_TYPE[tname], [len(d)] + d, src, off, nbytes,
                  len(sc), len(scales), qdim))
    scales.extend(sc)
    zps.extend(zp)

  gen.mkdir(parents=True, exist_ok=True)
  (gen / "layer_data.bin").write_bytes(bytes(blob) or b"\0" * 16)
  work, unit = _work(kind, dims, out_dims, opt)
  _write_header(gen / "layer_params.h", layer, rows, kind, descs, scales, zps,
                opt, act_bytes, work, unit, len(ins))
  _objcopy(gen)
  return kind, rows, work, unit, dims, out_dims


def _write_header(path, layer, rows, kind, descs, scales, zps, opt, act_bytes,
                  work, unit, n_in):
  def arr(vals, fmt):
    return ", ".join(fmt(v) for v in vals) if vals else "0"
  lines = [
      "// Generated by generate_layer.py; do not edit.",
      "#pragma once",
      "#include <cstdint>",
      "namespace layer {",
      f"constexpr int kOpIndex = {layer};",
      f"constexpr int kRows = {rows};",
      f'constexpr const char* kKind = "{kind}";',
      f"constexpr int kKindId = {KINDS.index(kind)};",
      f"constexpr int kNumInputs = {n_in};",
      f"constexpr int kNumTensors = {len(descs)};",
      f"constexpr uint32_t kActBytes = {max(act_bytes, 16)};",
      f"constexpr uint32_t kWork = {work};",
      f'constexpr const char* kWorkUnit = "{unit}";',
      "struct TensorDesc { int type; int dims[6]; int src; uint32_t offset;"
      " uint32_t bytes; int q_n; int q_off; int q_dim; };",
      "constexpr TensorDesc kTensors[] = {",
  ]
  for (ty, d, src, off, nb, qn, qo, qd) in descs:
    dd = ", ".join(str(x) for x in (d + [0] * 6)[:6])
    lines.append(f"  {{{ty}, {{{dd}}}, {src}, {off}u, {nb}u, {qn}, {qo}, {qd}}},")
  lines += [
      "};",
      f"constexpr float kScales[] = {{{arr(scales, lambda v: repr(float(v)) + 'f')}}};",
      f"constexpr int kZeroPoints[] = {{{arr(zps, str)}}};",
  ]
  for key in ("padding", "stride_w", "stride_h", "dil_w", "dil_h", "filter_w",
              "filter_h", "activation", "axis", "keep_dims", "keep_num_dims"):
    lines.append(f"constexpr int k_{key} = {int(opt.get(key, 0))};")
  lines.append("}  // namespace layer")
  path.write_text("\n".join(lines) + "\n")


def _objcopy(gen):
  subprocess.check_call(
      ["sparc-linux-objcopy", "-I", "binary", "-O", "elf32-sparc", "-B", "sparc",
       "--rename-section", ".data=.rodata,alloc,load,readonly,data,contents",
       "layer_data.bin", "layer_data.o"], cwd=gen)
  lib = gen / "liblayerblob.a"
  lib.unlink(missing_ok=True)
  subprocess.check_call(["sparc-linux-ar", "rcs", lib.name, "layer_data.o"],
                        cwd=gen)


def main():
  ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
  ap.add_argument("--layer", type=int, required=True)
  ap.add_argument("--rows", type=int, default=1)
  ap.add_argument("--gen", type=Path, required=True)
  a = ap.parse_args()
  kind, rows, work, unit, dims, out = generate(a.layer, a.rows, a.gen)
  print(f"layer: op={a.layer} kind={kind} rows={rows} work={work} unit={unit} "
        f"in={dims[0]} out={out}")


if __name__ == "__main__":
  main()
