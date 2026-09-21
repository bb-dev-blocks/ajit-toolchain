# cortos2 on qemu-ajit

cortos2 examples on **qemu-ajit** inside `ajit_build_dev`, beside the C-model.

C-model: `./build.sh` then `./run.sh` (`cortos_build/`). QEMU: `./build_qemu.sh` then `./run_qemu.sh` (`cortos_build_qemu/`).

qemu-ajit setup is the same as CoRTOS v1: `docs/cortos-on-qemu-ajit.md` (`setup_qemu.sh`, `ajit_env`).

## cortos2 qemu target

```bash
cd os/rtos/cortos2/examples/example_001
./build_qemu.sh    # cortos2 build --target qemu
./run_qemu.sh      # headless; match expected_uart.txt
```

- Default `cortos2 build` stays C-model. YAML RAM base is unchanged (`0x40000000` in the examples).
- `--target qemu` links at **`0x00100000`** (qemu-ajit RAM; PROM occupies `0`..`1MiB`), leaves the MMU off, and sets ELF `e_entry` to `_start`.
- UART stays the default AJIT map (`TX 0xFFFF3204`, `RX 0xFFFF3208`), which matches qemu-ajit.
- NCRAM has no separate qemu window. `--target qemu` packs each NCRAM region at the top of that RAM (a power-of-two size is aligned down). example_150's 16MB region lands at `0x07000000`. If the yaml RAM is smaller than its NCRAM (example_001 is 1MB RAM and two 16MB NCRAM regions), qemu widens that window to the 128MiB guest before packing. The C-model RAM size stays as written.
- `serial_in.txt`, if present, is written to the UART after the first guest line. The guest must enable the RX interrupt before that line. example_310 sends `q`.

## Coverage

| Example | C-model | qemu |
|---|---|---|
| example_001 | pass (`./build.sh && ./run.sh`, UART `Hello There`) | pass (`./build_qemu.sh && ./run_qemu.sh`, entry `0x00100000`) |
| example_005 | pass (`./build.sh && ./run.sh`, UART `005 sum 0`) | pass (`./run_qemu.sh`, entry `0x00100000`) |
| example_050 | pass (`./build.sh && ./run.sh`, both thread lines) | pass (`-smp 2`, both thread lines) |
| example_100 | pass (`./build.sh && ./run.sh`, both threads `final 8192`) | pass (`-smp 2`, both thread lines) |
| example_150 | pass (`./build.sh && ./run.sh`, sender 4, receiver sum 6) | pass (`-smp 2`, NCRAM `0x07000000`, same UART lines) |
| example_155 | pass (`./build.sh && ./run.sh`, sender 4, receiver sum 6) | pass (`-smp 2`, same UART lines) |
| example_200 | pass (`./build.sh && ./run.sh`, both threads `(15, 240)`) | pass (`-smp 2`, same UART lines) |
| example_210 | pass (`./build.sh && ./run.sh`, both threads `(15, 240)`) | pass (`-smp 2`, NCRAM `0x07000000`, same UART lines) |
| example_250 | pass (`./build.sh && ./run.sh`, `Message Sent!` / `Received Message!` / `Releasing Memory!`) | pass (`-smp 2`, same UART lines) |
| example_310 | pass (`./build.sh && ./run.sh`, `310 rx q exit 1`, `BYE(1)`) | pass (`serial_in.txt` `q`, same UART lines) |
| example_320 | pass (`./build.sh && ./run.sh`, four `Inside user_handler05.` lines) | pass (same UART line) |

## TFLite Micro

Thin projects under `os/rtos/cortos2/examples/tflite/`. They link the existing `tflite-micro/gen/ajit_sparc_default_gcc/lib/libtensorflow-microlite.a` (`TARGET=ajit`). Test sources stay in the submodule. CoRTOS v1 and bare-metal runs are in [tflite-on-qemu-ajit.md](tflite-on-qemu-ajit.md).

### How to run

Inside `ajit_build_dev`, from the toolchain root:

```bash
source ./set_ajit_home
source docker/ajit_build/ajit_env
```

The microlite archive must already exist (path above). Rebuild it only when it is missing:

```bash
cd tflite-micro
make -f tensorflow/lite/micro/tools/make/Makefile TARGET=ajit TARGET_ARCH=sparc microlite
```

Every example is `./build_qemu.sh` then `./run_qemu.sh`. Pass means exit 0 and every non-comment line of that directory's `expected_uart.txt` on the UART, including `~~~ALL TESTS PASSED~~~`. A `TEST()` suite also prints a ran-count line such as `[==========] 6 tests ran.`

```bash
# hello_world: qemu and C-model
cd os/rtos/cortos2/examples/tflite/hello_world
./build_qemu.sh && ./run_qemu.sh    # timeout 60s
./build.sh && ./run.sh              # C-model only here

# micro_speech: qemu only (6 tests, timeout 120s)
cd os/rtos/cortos2/examples/tflite/micro_speech
./build_qemu.sh && ./run_qemu.sh

# one kernel (timeout 180s). Names:
# conv depthwise_conv fully_connected softmax add pooling pad activations mul
# concatenation sub reshape squeeze quantize dequantize reduce
cd os/rtos/cortos2/examples/tflite/kernels/conv
./build_qemu.sh && ./run_qemu.sh

# person_detection: qemu only (1 test, timeout 300s)
cd os/rtos/cortos2/examples/tflite/person_detection
./build_qemu.sh && ./run_qemu.sh
```

`micro_speech`, the kernels, and `person_detection` have no C-model scripts. `hello_world` uses a 256KB stack; 64KB faulted the C-model stack guard. Leftover C-model: `pkill -x ajit_C_system_m`. Leftover qemu: `pkill -f qemu-system-sparc`.

Stock regression, unrelated to TFLite but required after a cortos2 change:

```bash
cd os/rtos/cortos2/examples/example_001
./build_qemu.sh && ./run_qemu.sh
```

### What the yaml does

Top-level keys, paths relative to `$AJIT_HOME`:

- `ExtraCc`: `.cc` files compiled with `sparc-linux-g++ -S -fno-pic`, then assembled.
- `ExtraIncludes`: extra `-I` for that compile.
- `ExtraLibDirs`: directories whose `.a` files are linked. Point this at the microlite lib dir.
- `Software.ProgramThreads[].CortosInitCalls`: `main` when the test has an explicit `main` (`hello_world`). `tflite_cortos_start` for `TEST()` suites. That symbol is in `os/rtos/cortos2/examples/tflite/cxxstub.cc`. It walks `.init_array` and `.ctors`, then calls `main`. SPARC g++ emits `.ctors`. Skipping the walk can print `~~~ALL TESTS PASSED~~~` with zero tests.

The linker keeps those arrays inside `.rodata`, and `ALIGN(4)` before the arrays so each constructor pointer is aligned. An unaligned pointer makes `tflite_cortos_start` hang with no UART. Each project directory still needs one `.c` file (`placeholder.c`). A yaml without `ExtraCc` stays on the C-only build.

### Coverage

| Example | C-model | qemu | Notes |
|---|---|---|---|
| `hello_world` | pass | pass | `CortosInitCalls: main`. RAM 4MB. |
| `micro_speech` | skip | pass | 6 `TEST()`s. `tflite_cortos_start`. RAM 8MB. C-model not run. |
| `kernels/conv` | skip | pass | 21 tests |
| `kernels/depthwise_conv` | skip | pass | 13 tests |
| `kernels/fully_connected` | skip | pass | 13 tests |
| `kernels/softmax` | skip | pass | 13 tests |
| `kernels/add` | skip | pass | 16 tests |
| `kernels/pooling` | skip | pass | 25 tests |
| `kernels/pad` | skip | pass | 11 tests |
| `kernels/activations` | skip | pass | 6 tests |
| `kernels/mul` | skip | pass | 9 tests |
| `kernels/concatenation` | skip | pass | 8 tests |
| `kernels/sub` | skip | pass | 15 tests |
| `kernels/reshape` | skip | pass | 8 tests |
| `kernels/squeeze` | skip | pass | 4 tests |
| `kernels/quantize` | skip | pass | 19 tests |
| `kernels/dequantize` | skip | pass | 3 tests |
| `kernels/reduce` | skip | pass | 44 tests |
| `person_detection` | skip | pass | 1 test. RAM 8MB. |

Kernel and `person_detection` projects use RAM 8MB, stack 256KB, and `tflite_cortos_start`. C-model is not run.
