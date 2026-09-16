# QEMU fork for AJIT SoC

We are maintaining this fork to test QEMU support for AJIT SoC which has a
sparcv8 processor and few peripherals like:

- UART
- Timer
- Interrupt controller
- I2C controller
- SPI controller
- Flash controller
- Ethernet controller

## Current Status

- We have achieved single core functional system where UART, Timer, & Interrupt
controller works.
- We will work on stabilizing this first & then move on to multi-core support.

---

## Build instructions for AJIT

```bash
mkdir build
cd build
../configure --target-list=sparc-softmmu
make -j8
```

- After the build you will find a `qemu-system-sparc` elf in the `build` folder.

---

## Running instructions for AJIT

```bash
cd build
./qemu-system-sparc -M ajit1_generic -cpu AJIT1 -serial pty -m 4G -nographic -gdb tcp:127.0.0.1:1234 -S -kernel ./a.out
```
- Connect to the serial console with `minicom -D /dev/pts/<x>`
    - Find out `<x>` from qemu monitor log where it says `char device redirected to /dev/pts/<x>`.
    - We are redirecting the serial console to another pseudo terminal in order to keep the monitor alive.
- P.S: `a.out` should be a baremetal binary.

### Enabling traces

- We currently have traces in:
    - UART register space r/w callbacks.
    - Timer register space r/w as well timer enabling, reset, & hit callbacks.
    - INTC register r/w callbacks as well are callbacks triggered on irq generation.

- To list all available `ajit1` traces, execute:
```
./qemu-system-sparc -d trace:help | grep ajit1
```

- Example usage:
```
./qemu-system-sparc --trace "ajit1_intc_write" --trace "ajit1_intc_read" --trace "ajit1_set_irq" \
--trace "ajit1_reset_irq" -M ajit1_generic -cpu AJIT1 -serial pty -m 4G -nographic -gdb tcp:127.0.0.1:1234 \
-S -kernel ~/workspace/redkill_tech/workspace/baremetal_tests/sparcv8/memory_rw.elf
```

## Open issues

- [Non-critical] Currently the ajit qemu instance drops into a qemu monitor
unlike the normal instances and also unlike LEON3. But I don't see any issues
in the functionality yet.
