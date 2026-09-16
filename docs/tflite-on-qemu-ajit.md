# TFLite Micro on qemu-ajit (bare-metal and CoRTOS)

Run **TensorFlow Lite Micro (TFLM)** tests as 32-bit SPARC V8 ELFs on **qemu-ajit** (`-M ajit1_generic -cpu AJIT1`). Two program models share one library:

| Path | OS | Build / run | Output ELF |
|---|---|---|---|
| **Bare-metal** | none (crt0 + trap table) | `./build_baremetal_qemu.sh` then `./run_baremetal_qemu.sh` | `baremetal_qemu/main.elf` |
| **CoRTOS** | CoRTOS, `--target qemu` | `./build_qemu.sh` then `./run_qemu.sh` | `cortos_build_qemu/main.elf` |

QEMU machine, RAM, and UART maps: [cortos-on-qemu-ajit.md](cortos-on-qemu-ajit.md). Container setup: [m3-ubuntu24-buildroot2025-arm64mac.md](m3-ubuntu24-buildroot2025-arm64mac.md).

This is **not** Linux qemu-user (`TARGET=sparc_generic` in the TFLM fork). That path is a different ABI and is not a pass gate for qemu-ajit.

## Fundamentals

TFLM is an **interpreter**, not an ahead-of-time compiler of the graph. A typical test:

1. Embeds the model as a C array (from a `.tflite` via `generate_cc_arrays.py`).
2. Registers the operators the graph needs (`MicroMutableOpResolver`).
3. Allocates a **static arena** (no `malloc` in the hot path).
4. Copies inputs, `Invoke()`, checks outputs.
5. Prints `~~~ALL TESTS PASSED~~~` through TFLM `DebugLog`.

On AJIT:

- CPU is **SPARC V8, 32-bit, big-endian**. Multi-byte weights in flatbuffers are byte-swapped into the arena (fork already does this).
- Firmware is **uClibc** `sparc-linux-g++` from Buildroot, **static**, **`-fno-pic -fno-pie`**. Default PIC left GOT relocs that zeroed TBR/stack after link.
- **RAM** for qemu-ajit programs starts at **`0x00100000`** (PROM uses the first 1MiB).
- **UART** for test text: control `0xFFFF3200`, TX `0xFFFF3204` (busy bit 8). TFLM `DebugLog` writes that MMIO. CoRTOS `printf` is a different path; these tests do not rely on it.
- The **same** archive `tflite-micro/gen/ajit_sparc_default_gcc/lib/libtensorflow-microlite.a` is linked for both bare-metal and CoRTOS.

CoRTOS examples are **C and flat**. TFLM is **C++**. The example directory therefore holds scripts and `config.yaml`, not a copy of the TFLM tree. Test bodies stay in the `tflite-micro` submodule.

C++ `TEST()` macros register cases in **static constructors**. SPARC g++ puts those in **`.ctors`**, not only `.init_array`. Bare-metal crt0 calls `tflite_call_ctors` before `main`. CoRTOS yaml must start `tflite_cortos_start` for `TEST()` suites (walks constructors, then `main`). If you skip that walk, UART can print `~~~ALL TESTS PASSED~~~` with **0 tests**. hello_world uses an explicit `main`, so `CortosInitCalls: main` is correct there.

## Layout

```text
$AJIT_HOME/                          # repos/ajit-toolchain in the container
  tflite-micro/                      # submodule, branch sparc-ajit
    tensorflow/lite/micro/ajit/debug_log.cc
    tensorflow/lite/micro/tools/make/targets/ajit_makefile.inc
    gen/ajit_sparc_default_gcc/      # gitignored build
  os/rtos/cortos/examples/tflite/
    crt0.S  cxxstub.cc  LinkerScript.qemu.txt
    build_baremetal_qemu.sh  run_qemu_elf.py  ensure_genfiles.sh
    hello_world/  micro_speech/  person_detection/  resnet50/  kernels/<name>/
```

Each child project: `config.yaml`, `expected_uart.txt`, `placeholder.c` (CoRTOS needs at least one `.c`), and the script pairs below. Generated: `baremetal_qemu/`, `cortos_build_qemu/`, `cortos_build/` (gitignored).

## Setup (inside `ajit_build_dev`)

```bash
source ./set_ajit_home
source docker/ajit_build/ajit_env
command -v qemu-system-sparc sparc-linux-g++
```

First TFLM build on a fresh container needs host Python and git (not in the image yet):

```bash
# as root, once per container
apt-get install -y git python3-numpy python3-pil
```

Build the interpreter library (once; example scripts also build it if missing):

```bash
cd tflite-micro
make -f tensorflow/lite/micro/tools/make/Makefile TARGET=ajit TARGET_ARCH=sparc microlite
sparc-linux-readelf -h gen/ajit_sparc_default_gcc/lib/libtensorflow-microlite.a
# Class ELF32, Machine Sparc
```

`make/downloads/` is gitignored; copy from a prior tree or let Make fetch (needs `git`).

## How to run

All commands below are from `$AJIT_HOME` after `set_ajit_home` and `ajit_env`. Pass: process exit 0 and every non-comment line of `expected_uart.txt` on UART stdout. Always include `~~~ALL TESTS PASSED~~~`. `TEST()` examples also expect a ran-count line (for example `[==========] 6 tests ran.`) so a 0-test false pass fails.

### Bare-metal qemu-ajit

No CoRTOS. crt0 sets PSR/WIM/TBR, clears BSS, runs constructors, calls `main`, then `ta 0`. Traps come from the CoRTOS trap table template.

```bash
cd os/rtos/cortos/examples/tflite/hello_world
./build_baremetal_qemu.sh
./run_baremetal_qemu.sh
```

`run_baremetal_qemu.sh` runs `qemu-system-sparc -M ajit1_generic -cpu AJIT1 -kernel baremetal_qemu/main.elf` with serial on stdio. Timeout: `TFLITE_QEMU_TIMEOUT` (default 60s; speech/person_detection scripts use 300s).

### CoRTOS qemu-ajit

CoRTOS still compiles C via `compileToSparcUclibc.py`. Extra C++ is `g++ -S` then `-s extra_cc_N.s`. Extra `.a` dirs are `-l`.

```bash
cd os/rtos/cortos/examples/tflite/hello_world
./build_qemu.sh    # cortos build --target qemu
./run_qemu.sh      # cortos run --target qemu
```

yaml (hello_world): `CortosInitCalls: main`, `ExtraCc` lists the test `.cc`, generated model `.cc`, and `cxxstub.cc`. Paths are relative to `$AJIT_HOME`. `TEST()` suites use `CortosInitCalls: tflite_cortos_start` instead of `main`.

Need a dummy `placeholder.c`; CoRTOS requires a C file even when entry is TFLM `main`.

### C-model (optional)

Same CoRTOS project, RAM start `0x0`, `cortos_build/`:

```bash
cd os/rtos/cortos/examples/tflite/hello_world
./build.sh && ./run.sh
```

hello_world passes. micro_speech is a **skip** (C-model stays at full CPU without test UART; qemu finishes in under a second). Kernel and person_detection C-model were not required. Leftover simulator: `pkill -x ajit_C_system_m` (binary name is `ajit_C_system_model`). Default `DebugLog` is the qemu UART map; the C simulator serial block is `0xFFFF3200`–`0xFFFF3213`. Rebuild DebugLog with `-DAJIT_UART_TX=0xFFFF3210` only if C-model logging is silent and you need that map.

## Shipped examples

| Directory | Bare-metal qemu | CoRTOS qemu | C-model | Notes |
|---|---|---|---|---|
| `hello_world` | pass | pass | pass | explicit `main` |
| `micro_speech` | pass | pass | skip | 6 `TEST()`s; generated wav/tflite arrays |
| `kernels/conv` | pass | pass | — | extra `conv_test_common.cc` + testdata |
| `kernels/depthwise_conv` | pass | pass | — | |
| `kernels/fully_connected` | pass | pass | — | |
| `kernels/softmax` | pass | pass | — | |
| `kernels/add` | pass | pass | — | |
| `kernels/pooling` | pass | pass | — | |
| `kernels/pad` | pass | pass | — | |
| `kernels/activations` | pass | pass | — | |
| `kernels/mul` | pass | pass | — | |
| `person_detection` | pass | pass | — | generated `.tflite` + `.bmp` arrays |
| `resnet50` | — | pending | skip | Qualcomm AI Hub TFLITE w8a8 ResNet-50; CoRTOS qemu only. Runbook: [tflite-micro/resnet50.md](tflite-micro/resnet50.md). Recipe for other models: [tflite-micro/README.md](tflite-micro/README.md). |

Kernel names: `conv`, `depthwise_conv`, `fully_connected`, `softmax`, `add`, `pooling`, `pad`, `activations`, `mul`.

```bash
# one kernel
cd os/rtos/cortos/examples/tflite/kernels/conv
./build_baremetal_qemu.sh && ./run_baremetal_qemu.sh
./build_qemu.sh && ./run_qemu.sh

cd os/rtos/cortos/examples/tflite/micro_speech
./build_baremetal_qemu.sh && ./run_baremetal_qemu.sh
./build_qemu.sh && ./run_qemu.sh

cd os/rtos/cortos/examples/tflite/person_detection
./build_baremetal_qemu.sh && ./run_baremetal_qemu.sh
./build_qemu.sh && ./run_qemu.sh

cd os/rtos/cortos/examples/tflite/resnet50
./fetch.sh && ./host_precheck.py
./build_qemu.sh && ./run_qemu.sh    # timeout 1800s; INPUT=<name>
```

Regression (must stay green): `cd os/rtos/cortos/examples/example_001 && ./build_qemu.sh && ./run_qemu.sh`.

## Adding another test

1. Keep the `*_test.cc` and model blobs in `tflite-micro`. Do not copy the TFLM tree into the example dir.
2. New directory under `os/rtos/cortos/examples/tflite/` (kernels under `kernels/<name>/`).
3. If the graph needs `.tflite` / `.wav` / `.bmp` arrays, set `TFLITE_GENERATOR_INPUTS` and call `ensure_genfiles.sh` (or let `build_baremetal_qemu.sh` generate). Output lives under `tflite-micro/gen/ajit_sparc_default_gcc/genfiles/`.
4. Bare-metal: `build_baremetal_qemu.sh` that exports `TFLITE_TEST_SRCS` (paths vs `$TFLM`) then `exec ../build_baremetal_qemu.sh`.
5. CoRTOS: `config.yaml` with `ExtraCc` (those `.cc` plus `cxxstub.cc`), `ExtraIncludes`, `ExtraLibDirs` pointing at `tflite-micro/gen/ajit_sparc_default_gcc/lib`. Start symbol: `main` or `tflite_cortos_start`.
6. `expected_uart.txt`: `~~~ALL TESTS PASSED~~~`. For `TEST()` add a ran-count line such as `[==========] 6 tests ran.`
7. Timeouts: speech/vision often need `cortos run --target qemu --timeout 300` and `TFLITE_QEMU_TIMEOUT=300`.

## Pitfalls

- **0 tests passed.** Constructors not run. Use `tflite_cortos_start` / crt0 ctor walk; keep `.ctors` in the linker script.
- **qemu hangs, no UART.** PIC/GOT, missing traps, or RAM not at `0x00100000`.
- **Undefined C++ delete.** Link `cxxstub.cc`.
- **`TARGET=ajit` without `TARGET_ARCH=sparc`.** Make may pick the host arch in `gen/`.
- **Do not** treat `sparc_generic` (qemu-user) or aparajit-root `aparajit-docker` TFLM scripts as this flow.

## Source pointers

- TFLM target: `tflite-micro/tensorflow/lite/micro/tools/make/targets/ajit_makefile.inc`
- UART log: `tflite-micro/tensorflow/lite/micro/ajit/debug_log.cc`
- Bare-metal link: `os/rtos/cortos/examples/tflite/{crt0.S,LinkerScript.qemu.txt,build_baremetal_qemu.sh}`
- CoRTOS C++: `os/rtos/cortos/src/cortos/sys/config.py` (`ExtraCc` keys), `files/build_sh/build_init.sh.tpl`, `files/linker_scripts/LinkerScript00.txt.tpl`
