# ResNet-50 w8a8 on cortos2 and qemu-ajit

Example: `os/rtos/cortos2/examples/tflite/resnet50/`.

Default JPEG is the first line of `inputs/order.txt` (`hopper`). Pass lines are `invoke: ok` and `top1: 457 bow tie`. The qemu cap is 700s. A hopper run finishes in about 90s. A quiet UART before the cap means the invoke is still running.

## How to run

Inside `ajit_build_dev`, from the toolchain root:

```bash
source ./set_ajit_home
source docker/ajit_build/ajit_env
```

The `sparc-ajit` microlite archive must exist. Build it once if it is missing:

```bash
cd tflite-micro
make -f tensorflow/lite/micro/tools/make/Makefile TARGET=ajit TARGET_ARCH=sparc microlite
```

Then:

```bash
cd os/rtos/cortos2/examples/tflite/resnet50
./host_precheck.py
./build_qemu.sh
./run_qemu.sh
```

Another still: `INPUT=panda ./build_qemu.sh && ./run_qemu.sh`, or `./build_qemu.sh tabby`. The build embeds that JPEG only.

`./host_precheck.py` needs `python3-numpy`, `python3-pil`, and `tflite_runtime`, `ai-edge-litert`, or TensorFlow. It writes `inputs/manifest.tsv` and `expected/<name>.txt`. `./build_qemu.sh` copies the selected file to `expected_uart.txt`.

Pass: exit 0, and every non-comment line of `expected_uart.txt` appears on the UART. Scores, shapes, and `timing:` are not pass keys. This build reports `ticks_per_sec=0`.

C-model is not a gate. Coverage row: [`cortos2-on-qemu-ajit.md`](../cortos2-on-qemu-ajit.md).

## How the w8a8 model is made to fit

The blob is Qualcomm AI Hub ResNet50 **TFLITE w8a8** (`resnet50_int8.tflite`, 26327248 bytes, sha256 `1753841ba8ce7ca250456db146d0d4c7035d9c15100ce3d2cb563cebde57eb22`). Pin and zip URL are in `model_pin.txt`. Fetch with `./fetch.sh`. Skip ONNX, DLC, and QNN from the same Hub page. The file starts with `TFL3`. Input is uint8 NHWC 1×224×224×3. Output is uint8 1×1000. Labels are the 1001-line TF list with `label_offset=1` (index 0 is the background class; the graph has 1000 classes).

`./generate_runtime.py` does three embeds:

- `sparc-linux-objcopy -I binary` packs the `.tflite` into `gen/libmodelblob.a` (`.rodata`). Symbols are `_binary_model_tflite_start` / `_end`.
- The selected JPEG is resized to 224×224 RGB and stored as a `uint8_t` C array. The interpreter scale is about 1/255; the bytes stay 0–255.
- `imagenet_labels.txt` becomes `gen/labels.cc`.

`config.yaml` is a normal cortos2 project: `CortosInitCalls: main`, stack 256 KiB, `FPU: No`, `RAM.SizeInMegaBytes: 128`. `ExtraCc` compiles `resnet50_main.cc`, the generated arrays, and `examples/tflite/cxxstub.cc` with `sparc-linux-g++ -S -fno-pic`. `ExtraLibDirs` points at `libtensorflow-microlite.a` (`TARGET=ajit`) and `gen/`. `main` uses `MicroMutableOpResolver` for the graph ops (Quantize, Sub, Mul, Pad, Conv2D, Concatenation, MaxPool2D, Add, Mean, FullyConnected).

SPARC V8 traps on an unaligned 8-byte load. FlatBuffers vectors in this file are not 8-byte aligned. The `sparc-ajit` tree's `flatbuffers.patch` copies those scalars with `memcpy`. Without that patch, `AllocateTensors` does not finish.

cortos2 links at `0x00100000` and runs a second layout pass from the ELF section sizes. `ExtraCc` passes `-fdata-sections`, so the 64 MiB `tensor_arena` is a `.bss.<name>` input section. The linker script gathers `*(.bss) *(.bss.*)` into the `.bss` output section. The second pass then places the stack after that block. On this build:

| Piece | Size or address |
|---|---|
| `.text` | 230164 bytes, from `0x100000` |
| `.rodata` (weights) | 26518136 bytes |
| `.bss` (arena plus small objects) | 67119608 bytes, `0x1a8b000`–`0x5a8dfff` |
| stack | 256 KiB at `0x5a92000` |
| guest | qemu `-m 128M` |

`arena_used` on hopper was 3107344 bytes. The static arena stays 64 MiB. Yaml RAM stays 128 MiB. `QEMU_GUEST_RAM_MIB` stays 128.

`cortos2 run --target qemu --timeout 700` boots `cortos_build_qemu/main.elf` and matches `expected_uart.txt`.
