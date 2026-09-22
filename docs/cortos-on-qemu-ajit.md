# CoRTOS on qemu-ajit

Run CoRTOS examples on **qemu-ajit** inside `ajit_build_dev`, or keep using the **C simulator**. Two builds; two script pairs.

C-model: `./build.sh` then `./run.sh` (unchanged). QEMU: `./build_qemu.sh` then `./run_qemu.sh` → `cortos_build_qemu/`.

## Setup (container)

Host packages for qemu live in `docker/ajit_base/setup_ajit_base.sh`. Rebuild `ajit_base` / `ajit_build_dev` after pulling those. On an **already running** container without those packages, install once as root (`ninja-build`, `pkg-config`, `meson`, `libglib2.0-dev`, `libpixman-1-dev`, …). `setup_qemu.sh` uses `apt-get` only with passwordless root/sudo.

```bash
# from repos/ajit-toolchain on the host
source ./set_ajit_home
# images already running: docker/ajit_build_dev/attach_shell.sh
```

Inside `ajit_build_dev`:

```bash
source ./set_ajit_home
source docker/ajit_build/ajit_env
./setup_qemu.sh
command -v qemu-system-sparc
qemu-system-sparc -M help | grep ajit1_generic
```

- Source: `$AJIT_HOME/qemu-ajit-v1.0` (copy of aparajit-root qemu-ajit; **do not** commit a `build/` dir there).
- Binary: `$AJIT_HOME/build/qemu-ajit-v1.0/qemu-system-sparc` (`PATH` via `ajit_env`).
- Not baked into the Docker image. Not part of `./setup.sh` (that script stays the C-model toolchain).

## CoRTOS qemu target

```bash
cd os/rtos/cortos/examples/example_001
./build_qemu.sh    # cortos build --target qemu
./run_qemu.sh      # headless; match expected_uart.txt
```

- Default `cortos build` is still C-model (`cortos_build/`, RAM start `0x0`).
- `--target qemu` links at **`0x00100000`** (qemu-ajit RAM; PROM occupies `0`..`1MiB`). C-model `--ramstart` 16MB-alignment does **not** apply. **Later:** maybe move qemu RAM to a 16MB-aligned base so both targets share one rule.
- UART: CoRTOS uses `ajit_access_routines_mt` defaults (`TX +0x04`, `RX +0x08` from `0xFFFF3200`), which match qemu-ajit. C-model scripts unchanged.
- QEMU run: `-M ajit1_generic -cpu AJIT1 -smp N -m MM -display none -serial stdio -monitor none -kernel cortos_build_qemu/main.elf`. `N` = `Cores * ThreadsPerCore` from `config.yaml` (capped at 4). `-m` is at least 128MiB and `TotalMemoryInKB`. No gdb wait. Timeout (default 30s; `example_sort` uses 300s). Exit 0 iff every non-comment line in `expected_uart.txt` appears on UART stdout.
- `cortos_exit` / `ta 0` with traps disabled **halts that qemu CPU** (AJIT `asr29` feature). It does not abort the whole VM, so the other AJIT thread can finish.
- QEMU does not enable the CoRTOS MMU path (identity physical map at `0x00100000`). C-model still enables MMU as before.
- `compileToSparcUclibc.py` links `-e main`; qemu `-kernel` uses ELF `e_entry`. QEMU `build.sh` runs `sparc-linux-objcopy --set-start` to `_start`.
- qemu-ajit `helper_rdasr29` must match CoRTOS (`0x50520000` for thread 0,0). Rebuild qemu after that C change (`./setup_qemu.sh`).
- Baremetal UART check: `os/rtos/cortos/examples/qemu_uart_probe.S` linked at `0x00100000`.
- `genVmapAsm` still requires 16MB-aligned L1 pages; qemu vmap uses `0x0` for that step only.

## Coverage

| Example | QEMU | Notes |
|---|---|---|
| `example_001` | pass | UART `Hello There`. |
| `example_stads` | pass | UART `Number of Stars:`. |
| `example_050` | pass | `-smp 2`. UART `050 thread 0,0` and `050 thread 0,1` (`cortos_printf`; yaml `LogLevel` is NONE). |
| `example_100` | pass | UART `VALUE_IS: 20`. |
| `example_150` | pass | UART `Sending Message 1` and `Received Message`. |
| `example_200` | pass | UART `Thread 0,0 finished` and `Thread 0,1 finished`. |
| `example_250` | pass | UART `Acquiring Memory!` and `Received Message!`. |
| `example_sort` | skip | `./build_qemu.sh` ok. `./run_qemu.sh` (300s) printed no UART. Two threads quicksort 1MiB of `char` with 8KiB stacks on TCG; no completion string in that window. Re-try with `cortos run --target qemu --timeout …` if you want a longer wait. |

If an example cannot run on qemu-ajit, replace `pending` with **skip** and state the reason here. No silent skip.

## TFLite Micro

How to run (bare-metal and CoRTOS), UART/ctors notes, and coverage: [tflite-on-qemu-ajit.md](tflite-on-qemu-ajit.md). ResNet-50 and bringing other models: [tflite-micro/README.md](tflite-micro/README.md). Tree: `os/rtos/cortos/examples/tflite/`.

## C-model regression

`example_{001,050,100,150,250}`: `./build.sh && ./run.sh` must still exit 0.
