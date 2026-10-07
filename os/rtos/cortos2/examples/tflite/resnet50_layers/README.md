# ResNet-50 per-layer harness (cortos2, C-model + qemu)

A full ResNet-50 inference on the Ajit C-model would take 7–11 days, so this
harness runs **one op at a time, cropped to a few output rows**. The op's cost
per unit of work is then scaled to the whole network from its topology.
The process, its logic, and the results are in aparajit
`docs/resnet50-metrics.md`. C-model metrics are described in
[`docs/cortos2-cmodel-metrics.md`](../../../../../../docs/cortos2-cmodel-metrics.md).

Each op runs through TFLM's own kernel registration (`Register_<OP>()`:
Init, Prepare, Invoke) linked from `libtensorflow-microlite.a`. A rebuilt or
optimized TFLM library is measured without changing the harness.

## Setup

Run inside the toolchain container, from `$AJIT_HOME`:

```bash
source ./set_ajit_home; source docker/ajit_build/ajit_env
export LD_LIBRARY_PATH=$AJIT_HOME/ahir/v2/functionLibrary/lib:$AJIT_HOME/ahir/v2/CtestBench/lib:$AJIT_HOME/ahir/v2/pipeHandler/lib:$LD_LIBRARY_PATH
cd os/rtos/cortos2/examples/tflite/resnet50_layers
```

Use `bash -c`, not `bash -lc`, with `docker exec`: a login shell resets
`LD_LIBRARY_PATH`, and the C-model then fails to find `libfpu.so`.

## List the layers

`layers.tsv` has one row per model op (82). Regenerate it with `./inventory.py`.

| Column | Meaning |
|---|---|
| `op` | op index in the model; use as `LAYER=` |
| `kind`, `config` | op kind; ops with the same shapes and options share a config id |
| `rep` | 1 for the representative op of a config (the one the sweep runs) |
| `stage` | stem, conv2..conv5, head |
| `in_shape`, `filter_shape`, `out_shape`, `stride`, `padding` | from the model |
| `macs`, `exec_macs` | all filter taps vs taps inside the image (SAME padding) |
| `work`, `work_unit` | cost unit: `exec_macs` (conv/FC), output elements, or input elements (MEAN) |

```bash
awk -F'\t' '$4==1' layers.tsv | cut -f1-3,8,14,15 | column -t   # representatives
```

## Run one layer

```bash
LAYER=46 ROWS=1 ./build.sh          # C-model build (default TARGET=cmodel)
LAYER=46 ROWS=1 ./run.sh            # runs, prints the metric table
```

`build.sh` variables:

| Variable | Default | Meaning |
|---|---|---|
| `LAYER` | required | op index from `layers.tsv` |
| `ROWS` | 1 | output rows to compute (input window cropped to match) |
| `TARGET` | `cmodel` | `cmodel` or `qemu` |
| `VARIANT` | `reference` | name of the kernel build; selects `work/<variant>/`, `logs/<variant>/`, `results/<variant>*.csv` |
| `TFLM_LIB_DIR` | `tflite-micro/gen/ajit_sparc_default_gcc/lib` | directory with `libtensorflow-microlite.a` (relative to `$AJIT_HOME` or absolute) |

The app prints:

```text
layer: op=46 kind=CONV_2D rows=1 work=8257536 unit=mac
invoke: ok
cycles: <C-model cycle estimate around Invoke>
checksum: <FNV-1a of the output tensor>
layer_done
```

The full log is in `logs/<variant>/L<op>_R<rows>.log`. `run.sh` prints the
whole-program counters from the C-model halt statistics plus the `app_*` lines.
Only `cycles:` (`app_cycles`) is specific to Invoke; the rest include boot,
Prepare and the input fill.

On qemu (fast, used for checksums and instruction counts):

```bash
TARGET=qemu LAYER=46 ROWS=1 ./build.sh && TARGET=qemu LAYER=46 ROWS=1 ./run.sh
```

The checksum must be identical on qemu and the C-model. The `cycles:` value
on qemu is not a cycle model.

How a layer is cropped (`generate_layer.py`): CONV_2D and MAX_POOL_2D compute
`ROWS` output rows over the full width from an input window of
`(ROWS-1)*stride + kernel` rows, with SAME padding turned into VALID on that
window. Elementwise ops, PAD, QUANTIZE, MEAN and CONCATENATION keep `ROWS`
rows of their activation inputs. FC is never cropped. Weights and bias are the
model's own data. Activations are a fixed pseudo-random fill (int8: zero
point + 0..31; float: [-2, 2)).

## Sweep

```bash
./sweep.sh all -j 4        # every representative op at ROWS=1 → results/<variant>.csv
./sweep.sh kinds           # one op of every non-conv kind
./sweep.sh linearity       # ops 9 and 46 at ROWS 1, 2, 4
./sweep.sh 8,46:2          # explicit list (op or op:rows)
```

Each C-model process keeps about 3.5 host cores busy, so pick `-j` as
cores / 3.5. The heaviest layers run first. For the `reference` variant,
`all` also writes `golden_checksums.tsv`. Other variants are checked
against that file, and a mismatch marks the row as not ok.

`./collect.py` rebuilds a results CSV from existing logs without rerunning.

## Instruction counts on qemu

```bash
./qemu_insn.py layers -j 4   # invoke instructions per representative op → results/<variant>-qemu-insn.csv
./qemu_insn.py model         # invoke instructions of the full ResNet-50 → results/qemu-model-insn.txt
```

Each count is exact. qemu runs twice with `libinsn.so` and
`libstoptrigger.so`: once stopping at the `call` to `Invoke`, once at its
return address. The difference is the instruction count. `model` uses the
unchanged `../resnet50` qemu build (run `../resnet50/build_qemu.sh` first).
The run takes a few hours with the plugin.

## Total estimate and qemu anchor

```bash
./estimate.py                # results/reference.csv (+ qemu files when present)
```

Prints cycles per config, stage and kind; the total invoke cycles; cycles per
MAC; and, given the qemu files, the weighted invoke CPI and the anchor check.
The anchor check compares the topology-scaled sum of per-layer qemu
instructions with the full-model qemu count, and the gate is ±15%. Per-op
numbers go to `results/<variant>-per-op.csv`.

## Evaluate a new kernel variant

1. Build TFLM with the new kernels into its own directory, e.g. with
   `OPTIMIZED_KERNEL_DIR=...` or a branch. Leave the default lib alone.
2. Sweep with the new library under a new variant name:
   ```bash
   VARIANT=myopt TFLM_LIB_DIR=/abs/path/to/lib ./sweep.sh all -j 4
   VARIANT=myopt ./qemu_insn.py layers -j 4    # optional, for CPI
   ```
3. Compare:
   ```bash
   ./compare.py reference myopt
   ./estimate.py --variant myopt
   ```
   `compare.py` refuses to report a speedup if any output checksum differs
   from `golden_checksums.tsv`: int8 kernels must be bit-exact.

## Vector-instruction estimate

ISA v2 SIMD (`VSMULD16`, `ADDDREDUCE16`, ...) is not in the C-model or the
FPGA prototype yet. `vector_estimate.py` applies the analytic model and
scenarios in `vector_assumptions.yaml` to the measured reference:

```bash
./vector_estimate.py --assumptions vector_assumptions.yaml
./vector_estimate.py --assumptions vector_assumptions.yaml --scenario scalar-identity   # must print 1.00x
./vector_estimate.py --assumptions vector_assumptions.yaml --per-config
```

Edit the YAML (or add a scenario) as the hardware and kernel design firm up.
Once real vector kernels exist, measure them with the variant flow above.

## Files

| File | Role |
|---|---|
| `inventory.py` → `layers.tsv` | model op list, configs, work |
| `generate_layer.py` | one op → `gen/layer_params.h` + cropped constant blob |
| `layer_main.cc`, `layer_runner.{h,cc}` | target app: build tensors, Init/Prepare/Invoke, print |
| `config.yaml.tpl`, `build.sh`, `run.sh` | cortos2 build/run of one layer in `work/<variant>/L<op>_R<rows>/` |
| `sweep.sh`, `collect.py` | many layers → `results/<variant>.csv`, `golden_checksums.tsv` |
| `qemu_insn.py` | exact invoke instruction counts on qemu |
| `estimate.py`, `compare.py` | topology total, variant comparison |
| `vector_estimate.py`, `vector_assumptions.yaml` | ISA v2 SIMD speedup estimate |
