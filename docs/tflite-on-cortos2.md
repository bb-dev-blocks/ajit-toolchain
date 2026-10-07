# TFLite Micro on cortos2: qemu and C-model

How to run every cortos2 TFLite Micro example under
`os/rtos/cortos2/examples/tflite/` on **qemu-ajit** and, where verified, on the
**Ajit C-model**. Background on the cortos2 qemu target, the yaml keys
(`ExtraCc`, `ExtraIncludes`, `ExtraLibDirs`) and the `.ctors` walk is in
[cortos2-on-qemu-ajit.md](cortos2-on-qemu-ajit.md#tflite-micro). C-model
counters and their meaning are in
[cortos2-cmodel-metrics.md](cortos2-cmodel-metrics.md).

## Setup

Inside `ajit_build_dev`, from the toolchain root:

```bash
source ./set_ajit_home
source docker/ajit_build/ajit_env
# C-model only: its shared libraries
export LD_LIBRARY_PATH=$AJIT_HOME/ahir/v2/functionLibrary/lib:$AJIT_HOME/ahir/v2/CtestBench/lib:$AJIT_HOME/ahir/v2/pipeHandler/lib:$LD_LIBRARY_PATH
```

From the host use `docker exec ... bash -c '...'`, not `bash -lc`. A login
shell resets `LD_LIBRARY_PATH`, and `ajit_C_system_model` then fails with
`libfpu.so: cannot open shared object file`.

All examples link `tflite-micro/gen/ajit_sparc_default_gcc/lib/libtensorflow-microlite.a`.
Build it only if it is missing:

```bash
cd tflite-micro
make -f tensorflow/lite/micro/tools/make/Makefile TARGET=ajit TARGET_ARCH=sparc microlite
```

## qemu (all examples)

Each example directory has `build_qemu.sh` (`cortos2 build --target qemu`,
output in `cortos_build_qemu/`) and `run_qemu.sh` (`cortos2 run --target qemu`
with a timeout). A run passes when it exits 0 and every non-comment line of the
directory's `expected_uart.txt` appears on the UART.

```bash
cd os/rtos/cortos2/examples/tflite/<example>
./build_qemu.sh && ./run_qemu.sh
```

| Example | Timeout | Pass line(s) |
|---|---|---|
| `hello_world` | 60 s | `~~~ALL TESTS PASSED~~~` |
| `micro_speech` | 120 s | `[==========] 6 tests ran.`, `~~~ALL TESTS PASSED~~~` |
| `person_detection` | 300 s | `~~~ALL TESTS PASSED~~~` |
| `kernels/<name>` | 180 s | `~~~ALL TESTS PASSED~~~` |
| `resnet50` | 700 s | `invoke: ok`, `top1: 457 bow tie` |
| `resnet50_layers` | 600 s | `invoke: ok`, `layer_done` |

Kernel names: `activations add concatenation conv depthwise_conv dequantize
fully_connected mul pad pooling quantize reduce reshape softmax squeeze sub`.

All kernels in one loop:

```bash
for k in os/rtos/cortos2/examples/tflite/kernels/*/; do
  (cd "$k" && ./build_qemu.sh >/dev/null && ./run_qemu.sh >/dev/null && echo "pass $k" || echo "FAIL $k")
done
```

`resnet50` first needs the model and images: `./fetch.sh` (see
[tflite-micro/resnet50-cortos2.md](tflite-micro/resnet50-cortos2.md)). Pass a
different image as `./build_qemu.sh <name>`.

`resnet50_layers` builds one ResNet-50 op at a time. It takes environment
variables rather than having `build_qemu.sh`:

```bash
cd os/rtos/cortos2/examples/tflite/resnet50_layers
TARGET=qemu LAYER=46 ROWS=1 ./build.sh && TARGET=qemu LAYER=46 ROWS=1 ./run.sh
```

See its [README](../os/rtos/cortos2/examples/tflite/resnet50_layers/README.md).

## C-model (verified examples)

`cortos2 build` without `--target` builds for the C-model into `cortos_build/`
(MMU on, RAM at the yaml address). `cortos2 run` supports qemu only, so the
C-model runs through the generated `cortos_build/run_cmodel.sh`. The program
halts the C-model with `ta 0` after its init calls return. The halt statistics
go to stderr and the app UART output to stdout.

### hello_world

```bash
cd os/rtos/cortos2/examples/tflite/hello_world
./build.sh && ./run.sh
```

`run.sh` checks `expected_uart.txt` against the C-model UART. It takes about
200 s and runs about 1.5M instructions. For the counters:
`./run.sh > /tmp/hello.log 2>&1; ../cmodel_metrics.py /tmp/hello.log expected_uart.txt`.

### resnet50_layers

```bash
cd os/rtos/cortos2/examples/tflite/resnet50_layers
LAYER=46 ROWS=1 ./build.sh && LAYER=46 ROWS=1 ./run.sh
```

`run.sh` removes the `-w` trace option, which makes the C-model about 5×
slower, then writes `logs/reference/L46_R1.log` and prints the metric table
(`cmodel_metrics.py`). `cycles:` is the C-model cycle estimate around the op's
Invoke. A 1-row layer takes minutes to over an hour depending on its MAC
count. `./sweep.sh all` runs every distinct layer configuration.

### Full ResNet-50: not practical

The full `resnet50` example executes about 3.2e11 instructions in Invoke. At
roughly 70k–700k simulated instructions per second, one C-model run would take
days. ResNet-50 C-model cycles are therefore measured per layer with
`resnet50_layers` and scaled to the network. The method and results are in
aparajit `docs/resnet50-metrics.md`.

## C-model: generic recipe (not verified per example)

For an example without C-model scripts (`micro_speech`, `person_detection`,
`kernels/*`):

```bash
cd os/rtos/cortos2/examples/tflite/<example>
cortos2 build                         # → cortos_build/
cd cortos_build
sed -i '/-w ${_MAIN}.wtrace/d' run_cmodel.sh   # optional: drop per-write trace (≈5× faster)
./run_cmodel.sh > ../cmodel.log 2>&1
cd .. && ../cmodel_metrics.py cmodel.log expected_uart.txt   # (kernels: ../../cmodel_metrics.py)
```

Things to check when bringing up a new example on the C-model:

- RAM: the C-model maps the yaml RAM size exactly (qemu always gives 128 MiB).
  Data, bss and stack must fit.
- Stack: `hello_world` needed 256 KB; 64 KB tripped the C-model stack guard.
- Time: estimate from the qemu instruction count (`libinsn.so`) at about
  70k–700k instructions/s. `TEST()` suites with many cases can take hours.
- Halt: the program must return from its init call (`main` or
  `tflite_cortos_start`), otherwise the C-model never prints statistics.
- Leftover processes: `pkill -x ajit_C_system_m`.

## Coverage

| Example | qemu | C-model |
|---|---|---|
| `hello_world` | pass | pass (`build.sh`, `run.sh`) |
| `micro_speech` | pass | not run (generic recipe) |
| `person_detection` | pass | not run (generic recipe) |
| `kernels/activations` | pass | not run (generic recipe) |
| `kernels/add` | pass | not run (generic recipe) |
| `kernels/concatenation` | pass | not run (generic recipe) |
| `kernels/conv` | pass | not run (generic recipe) |
| `kernels/depthwise_conv` | pass | not run (generic recipe) |
| `kernels/dequantize` | pass | not run (generic recipe) |
| `kernels/fully_connected` | pass | not run (generic recipe) |
| `kernels/mul` | pass | not run (generic recipe) |
| `kernels/pad` | pass | not run (generic recipe) |
| `kernels/pooling` | pass | not run (generic recipe) |
| `kernels/quantize` | pass | not run (generic recipe) |
| `kernels/reduce` | pass | not run (generic recipe) |
| `kernels/reshape` | pass | not run (generic recipe) |
| `kernels/softmax` | pass | not run (generic recipe) |
| `kernels/squeeze` | pass | not run (generic recipe) |
| `kernels/sub` | pass | not run (generic recipe) |
| `resnet50` | pass (`top1: 457 bow tie`) | impractical (days); use `resnet50_layers` |
| `resnet50_layers` | pass (all 40 layer configs) | pass (per layer; `sweep.sh`) |
