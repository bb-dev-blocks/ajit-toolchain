#!/usr/bin/env bash
# Fetch Qualcomm TFLITE w8a8 ResNet-50, five JPEGs, ImageNet labels.
# Model page (TFLITE w8a8 only): https://huggingface.co/qualcomm/ResNet50
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
cd "$HERE"

HUB_PAGE="https://huggingface.co/qualcomm/ResNet50"
ZIP_NAME="resnet50-tflite-w8a8.zip"
ZIP_URL="https://qaihub-public-assets.s3.us-west-2.amazonaws.com/qai-hub-models/models/resnet50/releases/v0.62.2/resnet50-tflite-w8a8.zip"
ZIP_SHA256="296580402848709ff13b1d5b4db8d1a5248e0dcc3bc2759076572c3bb323df7b"
MODEL="$HERE/resnet50_int8.tflite"

fetch() {
  local url="$1" dest="$2"
  if [[ -f "$dest" ]]; then
    echo "resnet50: have $dest"
    return 0
  fi
  echo "resnet50: GET $url"
  if command -v curl >/dev/null; then
    curl -fL --retry 3 -o "$dest" "$url"
  else
    wget -O "$dest" "$url"
  fi
}

find_zip() {
  local d="$HERE"
  local i
  for i in 1 2 3 4 5 6 7 8 9; do
    if [[ -f "$d/$ZIP_NAME" ]]; then
      echo "$d/$ZIP_NAME"
      return 0
    fi
    d="$(dirname "$d")"
  done
  return 1
}

unpack_w8a8() {
  local z="$1"
  echo "resnet50: extract $z"
  python3 - "$z" "$MODEL" <<'PY'
import sys, zipfile, pathlib
z, dest = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
inner = "resnet50-tflite-w8a8/resnet50.tflite"
with zipfile.ZipFile(z) as zf:
    data = zf.read(inner)
if b"TFL3" not in data[:16]:
    raise SystemExit("resnet50: zip member is not TFLite")
dest.write_bytes(data)
print(f"resnet50: wrote {dest} ({len(data)} bytes)")
PY
}

mkdir -p inputs expected

# Labels: 1001 lines, index 0 = background (TF Hub / slim). Model is 1000-class.
fetch "https://storage.googleapis.com/download.tensorflow.org/data/ImageNetLabels.txt" \
  imagenet_labels.txt

# Demo stills (public TensorFlow / ImageNet sample-image mirrors).
fetch "https://storage.googleapis.com/download.tensorflow.org/example_images/grace_hopper.jpg" \
  inputs/hopper.jpg
fetch "https://github.com/EliSchwartz/imagenet-sample-images/raw/master/n01440764_tench.JPEG" \
  inputs/tench.jpg
fetch "https://github.com/EliSchwartz/imagenet-sample-images/raw/master/n02102040_English_springer.JPEG" \
  inputs/spaniel.jpg
fetch "https://github.com/EliSchwartz/imagenet-sample-images/raw/master/n02123045_tabby.JPEG" \
  inputs/tabby.jpg
fetch "https://github.com/EliSchwartz/imagenet-sample-images/raw/master/n02510455_giant_panda.JPEG" \
  inputs/panda.jpg

if [[ -f "$MODEL" ]]; then
  echo "resnet50: have $MODEL ($(wc -c < "$MODEL") bytes)"
else
  zpath="$(find_zip || true)"
  if [[ -n "${zpath}" ]]; then
    unpack_w8a8 "$zpath"
  else
    fetch "$ZIP_URL" "$HERE/$ZIP_NAME"
    unpack_w8a8 "$HERE/$ZIP_NAME"
  fi
  if [[ ! -s "$MODEL" ]]; then
    echo "resnet50: zip did not yield a .tflite; trying Keras convert"
    python3 "$HERE/convert_keras.py"
  fi
fi

python3 - <<'PY'
from pathlib import Path
import hashlib
p = Path("resnet50_int8.tflite")
if not p.is_file() or p.stat().st_size < 1_000_000:
    raise SystemExit("resnet50: model missing or too small")
d = p.read_bytes()
if b"TFL3" not in d[:16]:
    raise SystemExit("resnet50: not a TFLite file")
print(f"resnet50: model {p.stat().st_size} bytes")
print("sha256", hashlib.sha256(d).hexdigest())
PY

cat > model_pin.txt <<EOF
file: resnet50_int8.tflite
bytes: $(wc -c < "$MODEL" | tr -d ' ')
sha256: $(python3 -c "import hashlib,pathlib; print(hashlib.sha256(pathlib.Path('resnet50_int8.tflite').read_bytes()).hexdigest())")
source: Qualcomm AI Hub ResNet50 TFLITE w8a8 (qai-hub-models resnet50 v0.62.2)
page: $HUB_PAGE
fetch: $HUB_PAGE  (download TFLITE w8a8 zip only)
zip: $ZIP_URL
zip_sha256: $ZIP_SHA256
zip_inner: resnet50-tflite-w8a8/resnet50.tflite
io: input uint8 NHWC 1x224x224x3 scale~1/255 zp=0; output uint8 1x1000
skip: ONNX, DLC, QNN packages from the same Hub page — TFLM needs this TFLite only
notes: torchvision ResNet-50, 1000-class ImageNet (index 0 = tench). Not Keras Caffe preprocess. Host precheck is the next gate (TFLM may still reject an op).
EOF

echo "resnet50: fetch done"
