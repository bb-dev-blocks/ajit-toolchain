# TFLite Micro on CoRTOS / qemu-ajit

Bring a `.tflite` onto AJIT: embed it, link `libtensorflow-microlite.a`, run under CoRTOS on qemu-ajit.

Worked examples: [resnet50.md](resnet50.md) (CoRTOS v1) and [resnet50-cortos2.md](resnet50-cortos2.md) (cortos2 on qemu-ajit).

## Recipe (any model)

1. **Runtime.** Inside `ajit_build_dev`: `source ./set_ajit_home`; `source docker/ajit_build/ajit_env`. Build microlite once:
   `cd tflite-micro && make -f tensorflow/lite/micro/tools/make/Makefile TARGET=ajit TARGET_ARCH=sparc microlite`
2. **Model.** Prefer a TFLM-friendly 8-bit `.tflite`. ResNet-50: https://huggingface.co/qualcomm/ResNet50 (TFLITE w8a8 zip only; skip ONNX/DLC/QNN). Keep the `.tflite` as the source blob. Do not commit generated C arrays, `objcopy` `.a` files, or the Hub zip.
3. **CoRTOS project.** Copy the ResNet-50 example layout: `config.yaml` with `ExtraCc` / `ExtraIncludes` / `ExtraLibDirs`, `TotalMemoryInKB` large enough for weights plus arena, `CortosInitCalls: main` for an explicit `main`.
4. **Embed.** At build, `objcopy -I binary` the `.tflite` into a `.a` (large models) or TFLM `generate_cc_arrays.py` (small models). Preprocess the chosen input to a C byte array.
5. **Ops.** Register every opcode the model uses (`MicroMutableOpResolver`). Missing op: another export of the same net, then enable or write a TFLM **reference** kernel on `sparc-ajit`.
6. **Inputs.** Optional build-time `INPUT=<name>` if you keep several samples. Convert only the selected file.
7. **Host check.** Run the same `.tflite` + samples with TFLite/TFLM on x86. Freeze expected UART (invoke + top-1). Then qemu.
8. **Run.** `./build_qemu.sh` then `./run_qemu.sh`. Pass = every non-comment line of `expected_uart.txt` appears on UART. Increase `--timeout` for large nets (ResNet-50 uses 600s).
9. **Do not** use the AJIT C-model as a gate for large nets.

Coverage ledger: [`cortos-on-qemu-ajit.md`](../cortos-on-qemu-ajit.md).
