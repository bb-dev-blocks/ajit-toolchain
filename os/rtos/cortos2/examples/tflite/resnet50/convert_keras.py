#!/usr/bin/env python3
"""Fallback: Keras ImageNet ResNet50 → int8 TFLite using the five JPEGs as calib."""

from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "resnet50_int8.tflite"


def main():
  import numpy as np
  import tensorflow as tf
  from PIL import Image
  from tensorflow.keras.applications.resnet50 import ResNet50, preprocess_input

  model = ResNet50(weights="imagenet")
  jpegs = []
  order = (HERE / "inputs" / "order.txt").read_text().splitlines()
  for line in order:
    name = line.strip()
    if not name or name.startswith("#"):
      continue
    p = HERE / "inputs" / f"{name}.jpg"
    if p.is_file():
      jpegs.append(p)
  if not jpegs:
    raise SystemExit("resnet50: no JPEGs for representative dataset")

  def representative():
    for p in jpegs:
      im = Image.open(p).convert("RGB").resize((224, 224), Image.BILINEAR)
      arr = np.asarray(im, dtype=np.float32)
      arr = preprocess_input(arr)
      yield [np.expand_dims(arr, 0)]

  converter = tf.lite.TFLiteConverter.from_keras_model(model)
  converter.optimizations = [tf.lite.Optimize.DEFAULT]
  converter.representative_dataset = representative
  converter.target_spec.supported_ops = [tf.lite.OpsSet.TFLITE_BUILTINS_INT8]
  converter.inference_input_type = tf.uint8
  converter.inference_output_type = tf.uint8
  blob = converter.convert()
  OUT.write_bytes(blob)
  print(f"resnet50: wrote {OUT} ({len(blob)} bytes) from Keras ResNet50")


if __name__ == "__main__":
  main()
