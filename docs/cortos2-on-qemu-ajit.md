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
- NCRAM has no separate qemu window. `--target qemu` packs each NCRAM region at the top of that RAM (a power-of-two size is aligned down). example_150's 16MB region lands at `0x07000000`.
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
