# ResNet-50 (int8 ImageNet) on CoRTOS + qemu-ajit

Example dir: `os/rtos/cortos/examples/tflite/resnet50/`.

## Once

```bash
source ./set_ajit_home
source docker/ajit_build/ajit_env
cd tflite-micro
make -f tensorflow/lite/micro/tools/make/Makefile TARGET=ajit TARGET_ARCH=sparc microlite
```

Host/container extras: `python3-numpy`, `python3-pil`, and `tflite_runtime` / `ai-edge-litert` / TensorFlow (for `./host_precheck.py`). Keras convert fallback needs TensorFlow.

## Fetch (host or container)

```bash
cd os/rtos/cortos/examples/tflite/resnet50
chmod +x fetch.sh build_qemu.sh run_qemu.sh
./fetch.sh
```

Source model is Qualcomm AI Hub ResNet50 **TFLITE w8a8**. Fetch reference: https://huggingface.co/qualcomm/ResNet50 (download the TFLITE w8a8 zip only; skip ONNX/DLC/QNN). `./fetch.sh` unpacks that zip (local copy or the AI Hub zip URL) to `resnet50_int8.tflite`. Pin: `model_pin.txt`.

Keeps `resnet50_int8.tflite` (committed), five JPEGs under `inputs/`, `imagenet_labels.txt` (1001 lines; 1000-class output uses offset 1). Derived files go in `gen/` (gitignored). Do not commit the zip.

## Host precheck

```bash
./host_precheck.py
```

Writes `inputs/preprocess_spec.json`, `inputs/manifest.tsv`, and `expected/<name>.txt` (stable UART lines).

## Build and run (container)

Default input is the first row of `inputs/order.txt` (`hopper`).

```bash
./build_qemu.sh
./run_qemu.sh          # --timeout 600
```

Other still:

```bash
INPUT=panda ./build_qemu.sh
./run_qemu.sh
# or
./build_qemu.sh tabby && ./run_qemu.sh
```

Pass: UART contains `invoke: ok` and `top1: <id> <label>` from `expected/<input>.txt`. Extra lines (shapes, arena, `rank1`–`rank5` with scores, timing, per-op `tflm: invoke N/M`) are for analysis. The pass line is `top1:` after the ranks so the qemu matcher does not stop on a scored line.

SPARC V8 traps on unaligned 8-byte loads. TFLM’s FlatBuffers `Vector::Get` for `int64` zero-points used an unaligned load (vector payload starts 4 bytes after `size`). `flatbuffers.patch` now `memcpy`s scalars. Without that, `AllocateTensors` hangs in QUANTIZE prepare.

C-model is not a gate. Bare-metal qemu is not required unless CoRTOS is blocked.

## Layout

| Path | Role |
|---|---|
| `resnet50_int8.tflite` | Qualcomm TFLITE w8a8 blob (commit) |
| `model_pin.txt` | sha256, https://huggingface.co/qualcomm/ResNet50, zip URL, I/O notes |
| `inputs/*.jpg` | Five selectable stills |
| `inputs/order.txt` | Default `INPUT` is first name |
| `generate_runtime.py` | `objcopy` model, embed selected JPEG |
| `resnet50_main.cc` | TFLM `main`, verbose UART |
| `docs/tflite-micro/` | This runbook + generic recipe |
