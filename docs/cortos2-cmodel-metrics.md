# cortos2 on the Ajit C-model: metrics

What `ajit_C_system_model` reports for a cortos2 program, what each number means, and how to collect it. Numbers below come from `example_001`, the TFLM `hello_world`, and a compute loop, run in `ajit_build_dev`.

## Run

```bash
# from repos/ajit-toolchain/docker/ajit_build_dev: ./attach_shell.sh
source ./set_ajit_home
source docker/ajit_build/ajit_env
export LD_LIBRARY_PATH=$AJIT_HOME/ahir/v2/functionLibrary/lib:$AJIT_HOME/ahir/v2/CtestBench/lib:$AJIT_HOME/ahir/v2/pipeHandler/lib:$LD_LIBRARY_PATH

cd os/rtos/cortos2/examples/example_001
./build.sh                      # cortos2 build (default target: cmodel), output in cortos_build/
./run.sh > run.log 2>&1         # app UART on stdout, halt statistics on stderr
../tflite/cmodel_metrics.py run.log            # metric table
../tflite/cmodel_metrics.py --csv run.log      # one CSV row
../tflite/cmodel_metrics.py run.log expected_uart.txt   # also require UART lines
```

- `LD_LIBRARY_PATH`: `ajit_env` points at `ahir_release/functionLibrary/lib`, which is absent in the current image; the C-model needs `libfpu.so`, `libSockPipes.so`, `libPipeHandlerDebugPthreads.so` from `ahir/v2`. Without the export the run fails with `libfpu.so: cannot open shared object file`.
- Use a non-login shell (`docker exec ... bash -c`). `bash -lc` resets `LD_LIBRARY_PATH`.
- The run ends when cortos2 executes `ta 0` after the init calls return (`init_footer.s.tpl`). The C-model prints `Program exited with a trap type = 0x0`, the statistics, and exits.
- Leftover simulator after an interrupted run: `pkill -x ajit_C_system_m`.

## Metrics

| Metric | Parser key | Source line in the log | Meaning |
|---|---|---|---|
| Instructions | `instructions` | `number-of-instructions-executed` | Instructions retired by core 0 thread 0, boot included. |
| Cycles | `cycles` | `cycle-count estimate` | C-model estimated cycles (formula below). |
| CPI | `cpi` | computed | `cycles / instructions`. |
| Traps | `traps` | `number-of-traps` | Window overflow/underflow, `ta`, interrupts. Each costs 16 cycles in the estimate. |
| Control transfers | `cti`, `cti_mispredicts` | `number-of-cti = N, mispredicts=M` | Branches, calls, jumps; mispredicts cost 4 cycles each. |
| Return-address mispredicts | `ras_mispredicts` | `RAS: ... mispredicts=` | Return-address stack misses (diagnostic; not in the estimate). |
| MMU | `mmu_bypass_accesses`, `mmu_translated`, `mmu_tlb_hits`, `tlb_misses` | `Mmu statistics for core=0, thread=0` | Accesses with the MMU off, translated accesses, TLB hits; misses cost 250 cycles each. |
| I-cache | `icache_accesses/hits/misses` | `Statistics for ICACHE core-id=0` | Misses cost 70 cycles each. |
| D-cache | `dcache_accesses/hits/misses`, `dcache_read_*`, `dcache_write_*` | `Statistics for DCACHE core-id=0` | Misses cost 70 cycles each. Nearly every write misses (write-through, no write-allocate), so stores are expensive in the estimate. |
| Wall-clock | `wall_s` | `Total time taken by testbench: N secs` | Host seconds. |
| Simulator speed | `instr_per_s` | computed | Instructions per host second. |
| App region cycles | `app_cycles` | app prints `cycles: N` | Delta of `cortos_get_clock_time()` around the region of interest. |

### How the cycle estimate is computed

`getCycleEstimate()` in `AjitPublicResources/processor/64bit/C_multi_core_multi_thread/cpu/src/AjitThread.c`, constants in `common/include/Ajit_Hardware_Configuration.h`:

```text
cycles = instructions
       + 70  x (icache misses + dcache misses)
       + 250 x (MMU translated accesses - TLB hits)
       + 16  x traps
       + 4   x CTI mispredicts
       + 30  x integer divides
       + 16/24 x single/double FP div and sqrt
```

It is a penalty model on top of one cycle per instruction, not a pipeline simulation. `example_001` reproduces it to within 0.1%.

### Reading cycles from the program

`%asr30` (low) and `%asr31` (high) return the same estimate at that instant. cortos2 exposes it as `cortos_get_clock_time()` (`__ajit_get_clock_time()`):

```c
uint64_t t0 = cortos_get_clock_time();
/* region */
uint64_t t1 = cortos_get_clock_time();
cortos_printf("cycles: %u\n", (uint32_t)(t1 - t0));
```

`CORTOS_DEBUG` already prints this clock in brackets, e.g. `main() [4474913]`.

Use region deltas, not run totals, for small programs: until cortos2 turns the MMU on, every fetch is uncacheable and counts as a miss. In `example_001`, 63678 of the accesses happen with the MMU off, which is why its whole-run CPI is 69.

### Not kept

- L2 statistics: L2 is off by default (`-L 0`), nothing is printed.
- MMIO performance counters (`__ajit_sample_thread_performance_counters`): FPGA counters; not used for C-model figures.
- TFLM profiler ticks: TFLM has no timer on this target and prints `0`.
- Branch-predictor table and RAS push/pop counts: diagnostic dumps, not workload metrics.

## Results

Default C-model flags from `run_cmodel.sh` (I/D cache 512 lines, direct-mapped, no L2, branch predictor 16 entries). The first two rows ran with the generated `-w main.wtrace`, which only changes wall-clock time, not the counts.

| Workload | Instructions | Cycles | CPI | I-miss | D-miss | Traps | Wall | Speed |
|---|---|---|---|---|---|---|---|---|
| `example_001` (whole run) | 65,203 | 4,499,929 | 69.0 | 50,702 | 12,601 | 6 | 8 s | 8.2k instr/s |
| tflite `hello_world` (whole run, pass) | 1,537,051 | 11,004,745 | 7.16 | 99,452 | 27,848 | 5,828 | 195 s | 7.9k instr/s |
| 20M-instruction compute loop, run without `-w` | 20,054,972 | 24,484,480 | 1.22 | 50,671 | 12,587 | 6 | 296 s | 67.8k instr/s |

The compute loop's in-app region measured 20,000,102 cycles for 20,000,000 loop instructions: CPI 1.0 when everything hits.

A real kernel, ResNet-50 op 69 (1×1 conv, stride 2, 1024→2048, one output row) in the `resnet50_layers` harness: whole run 1,179,957,986 instructions, 1,478,593,542 cycles, 4,557 s (259k instr/s). The `Invoke` region took 1,354,707,886 cycles for 1,177,185,661 instructions (counted on qemu), so the invoke CPI is 1.15. Most extra cycles come from branch mispredicts and I-cache misses.

## Simulator speed

- The generated `run_cmodel.sh` passes `-w main.wtrace` (a log of every register and memory write). That limits the model to about 12k instructions per second.
- Without `-w`, it runs at about 68k instructions per second on the compute loop. ResNet-50 conv layers ran at 150k–730k instructions per second; the rate falls with host load. The C-model libraries are already built `-O3`.
- Each `ajit_C_system_model` process keeps about 3.5 host cores busy (spinning threads), so run about cores / 3.5 simulations in parallel.
- At 68k instr/s, one second of host time is about 0.14 ms of a 500 MHz Ajit. Workloads of billions of instructions take days; a full ResNet-50 inference is 3.2e11 instructions. Measure representative regions instead. See `os/rtos/cortos2/examples/tflite/resnet50_layers/`.
- `-I <n>` prints wall-clock time and the cycle estimate every `n` instructions, useful as a progress meter on long runs.
