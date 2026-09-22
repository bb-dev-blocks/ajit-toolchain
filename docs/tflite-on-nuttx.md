# TFLite Micro on single-core NuttX

`ajit1-qemu:tflite` is a single-core NuttX image for qemu-ajit. It boots to the `nsh>` prompt and runs four TensorFlow Lite Micro programs from `/tflite/`. `ajit1-qemu:nsh` and `ajit1-qemu:smp` are unchanged.

The interpreter is the existing archive `tflite-micro/gen/ajit_sparc_default_gcc/lib/libtensorflow-microlite.a` (`TARGET=ajit`, `sparc-linux-`). Model bytes stay in the toolchain tree. The NuttX image does not carry a second committed copy.

## What you can run

All four programs are on one image. Each program is an executable. The model stays inside that executable. You pass a file path. One command runs at a time.

`cat /tflite/README.md` prints the same instructions on the booted image. With no argument, or with `help`, each program prints usage and does not run.

| Command | Input file | Pass line |
|---|---|---|
| `/tflite/hello_world` | `/tflite/inputs/hello_world/0`, `1`, `2` | `hello_world: x=0 y=...`, `x=1.57`, `x=3.14`. `abs(y - sin(x)) <= 0.05` |
| `/tflite/micro_speech` | `/tflite/inputs/micro_speech/yes`, `no` | `micro_speech: yes` or `micro_speech: no` |
| `/tflite/person_detection` | `/tflite/inputs/person_detection/person`, `no_person` | `person_detection: person` or `person_detection: no person` (higher score) |
| `/tflite/resnet50` | `/tflite/inputs/resnet50/hopper`, `tench`, `spaniel`, `tabby`, `panda` | `top1: 457 bow tie`, `0 tench`, `217 English springer`, `285 Egyptian cat`, `388 giant panda` |

Hello files are text (`0`, `1.57`, `3.14`). Speech files are 16000 big-endian int16 samples (1000 ms). Person files are 9216 raw bytes (96×96). ResNet files are 150528 raw bytes (224×224×3). A missing file or `help` prints `usage:` and does not run the model. `ls /tflite` lists the four program names. A bare name such as `hello_world 0` is not a command.

`tflm:` lines on the same UART are the interpreter's own log. The pass line is the `printf` from the program.

## Adding your own inputs

Put files in `tflite-inputs/` at the toolchain root (`repos/ajit-toolchain/tflite-inputs` on the host, `/home/ajit/ajit-toolchain/tflite-inputs` in the container). The build copies that tree onto `/tflite/inputs/`. The shipped samples stay. A file with the same relative path replaces the shipped sample.

```text
tflite-inputs/hello_world/half          -> /tflite/inputs/hello_world/half
tflite-inputs/micro_speech/clip         -> /tflite/inputs/micro_speech/clip
tflite-inputs/person_detection/scene    -> /tflite/inputs/person_detection/scene
tflite-inputs/resnet50/mypic            -> /tflite/inputs/resnet50/mypic
```

Then run `./scripts/run-nuttx-ajit.sh tflite`. If the tflite image is already built, that script rebuilds it when anything under `tflite-inputs/` is newer than `nuttx/nuttx`. `make` in `nuttx/` does the same when that config is selected. The folder is gitignored.

The whole `/tflite` volume, shipped samples included, must stay within 8 MiB. A larger volume fails the build and prints the size.

Each program reads one file and checks its shape. A file of the wrong size prints `usage:` and does not run.

### hello_world

A text file with one decimal number, the value of `x`. A trailing newline is fine. The program prints `hello_world: x=<x> y=<y>` with `y` near `sin(x)`. The shipped files are `0`, `1.57`, and `3.14`.

### micro_speech

Raw mono PCM. 16000 samples per second, signed 16-bit, most significant byte first, exactly 16000 samples (32000 bytes, one second). The program turns that clip into features (40 values, 49 frames, 30 ms window, 20 ms stride) and prints the winning label: `silence`, `unknown`, `yes`, or `no`.

### person_detection

Raw grayscale image. 96 rows, 96 columns, one byte per pixel, row by row, 9216 bytes, no header. The program copies those bytes into the int8 image tensor and prints `person` or `no person`, whichever score is higher.

### resnet50

Raw RGB image, matching `os/rtos/cortos2/examples/tflite/resnet50/inputs/preprocess_spec.json`:

| Field | Value |
|---|---|
| Size | 224 × 224 |
| Layout | row by row, then R, G, B for each pixel |
| Type | one byte per channel, values 0–255 |
| Length | 150528 bytes, no header |
| Channel order | RGB |
| Mean | 0, 0, 0 |
| Std | 1, 1, 1 |
| `label_offset` | 1 (ImageNet index 0 is `tench`; the background line is dropped) |

Leave pixel values in 0–255. The model applies its own scale (`0.003921568859368563`, zero point 0). Do not scale the file to 0–1, and do not swap to BGR.

From a JPEG, write that byte file with the cortos2 helper (bilinear resize to 224×224):

```bash
python3 - <<'PY'
import sys
from pathlib import Path
sys.path.insert(0, "os/rtos/cortos2/examples/tflite/resnet50")
from preprocess import jpeg_to_bytes, load_spec
root = Path("os/rtos/cortos2/examples/tflite/resnet50")
spec = load_spec(root / "inputs" / "preprocess_spec.json")
dest = Path("tflite-inputs/resnet50/mypic")
dest.parent.mkdir(parents=True, exist_ok=True)
dest.write_bytes(jpeg_to_bytes(Path("photo.jpg"), spec))
PY
```

Run it from the toolchain root. Then:

```text
/tflite/resnet50 /tflite/inputs/resnet50/mypic
```

The program prints `top1: <id> <label>` using `imagenet_labels.txt` after `label_offset` 1.

## Why this image is 128 MiB

QEMU is started with `-m 128M -smp 1`. Guest RAM begins at `0x00100000` (the first 1 MiB is PROM).

`ajit1-qemu:nsh` keeps a 16 MiB link (`boards/sparc/ajit1/ajit1-qemu/scripts/linksparc.ld`, `CONFIG_RAM_SIZE=16777216`). ResNet-50 does not fit there: the int8 file is about 25 MiB and the arena is 64 MiB.

`ajit1-qemu:tflite` uses `configs/tflite/defconfig` (`CONFIG_RAM_SIZE=134217728`, `CONFIG_AJIT1_QEMU_TFLITE=y`) and `scripts/linksparc-128m.ld` (`ram` origin `0x00100000`, length 128M). `_RAM_END` for that image is `0x08100000`. The 16 MiB script still ends at `0x01100000`.

## How the programs are exposed

NSH runs a builtin of the same name before it looks up a file. Registering `hello_world` as a builtin would make the bare name work, and a builtin filesystem would also list `hello`, `nsh`, and `sh`.

The board mounts a ROMFS at `/tflite` from `board_late_initialize`. That volume holds `README.md`, the input files under `/tflite/inputs/`, and a placeholder file for each program. A small binfmt accepts only `/tflite/hello_world`, `/tflite/micro_speech`, `/tflite/person_detection`, and `/tflite/resnet50`, and starts the linked program. Any other path returns "not found". The sources are `src/ajit1_tflite_dir.c` and the four `*.cxx` files under `nuttx/boards/sparc/ajit1/ajit1-qemu/src/`. They are not under Apache `apps`. `scripts/gen-nuttx-tflite-fs.py` builds the ROMFS.

## How C++ is linked

The final link is `sparc-linux-ld`, not `g++`, and it does not pull libstdc++.

- Sized `operator delete` and `putchar_` live in `src/cxxstub.cxx`. `putchar_` writes UART TX `0xFFFF3204` (control `0xFFFF3200`), which is where the microlite `printf` and `DebugLog` send text. NSH `printf` is a separate path and is what the pass lines use.
- The signal kernels call glibc `__errno_location`. The stub forwards that to NuttX `__errno`.
- `linksparc-128m.ld` lays out `.init_array` and `.ctors` as a flat 4-byte-aligned list between `_sinit` and `_einit`. `CONFIG_HAVE_CXXINITIALIZE` walks that list once. The 16 MiB script is not changed.
- The board `src/Makefile` compiles the `*.cxx` files with `sparc-linux-g++` (`CROSSDEV=sparc-linux-`) and the same flags as the microlite archive (`-m32 -mcpu=v8`, no RTTI, no exceptions, `TF_LITE_STATIC_MEMORY`). Those objects are archived into `libboard.a`.

## Where the model bytes come from

Hello, micro speech, and person detection include the model `.cc` arrays from `tflite-micro/gen/ajit_sparc_default_gcc/genfiles/`. The input arrays in that tree are not linked. The ROMFS script turns them into files: hello text, speech as big-endian int16, person images as raw bytes. Speech runs the audio preprocessor, then the classifier. Person detection compares the person and no-person int8 scores. Hello is the int8 sine model.

ResNet-50 reads the cortos2 example, and does not modify it:

- `os/rtos/cortos2/examples/tflite/resnet50/resnet50_int8.tflite`
- the five JPEGs named in `inputs/order.txt`
- `inputs/preprocess_spec.json` (uint8 224×224, `label_offset` 1)
- `imagenet_labels.txt`

`scripts/gen-nuttx-resnet50.py` writes the label table and `sparc-linux-objcopy`s the `.tflite` into `libmodelblob.a`. `scripts/gen-nuttx-tflite-fs.py` preprocesses every JPEG into a raw file on the ROMFS and objcopies that volume into `libromfs.a`. Output goes to `nuttx/boards/sparc/ajit1/ajit1-qemu/src/resnet_gen/`, which is gitignored. If `resnet50_int8.tflite` is missing, the model script exits non-zero and prints the path. The ResNet arena is 64 MiB, cleared at the start of each command.

## Setup

Use the already running `ajit_build_dev` container. Do not run `docker/ajit_build_dev/run.sh` while that container is up; it removes the container.

```bash
docker exec -w /home/ajit/ajit-toolchain ajit_build_dev bash -lc \
  'source ./set_ajit_home && source docker/ajit_build/ajit_env && bash'
```

Host `kconfig-tweak` is not required. The script runs inside the container, where that tool is installed.

## Manual session

```bash
./scripts/run-nuttx-ajit.sh tflite
```

If `nuttx/nuttx` is missing, or it is the `nsh` or `smp` image, this builds `ajit1-qemu:tflite` and then starts QEMU. If `tflite-inputs/` is newer than an existing tflite image, it rebuilds before QEMU. `nsh` and `smp` do the same for their own configs, without that input folder. The compiler is `sparc-linux-` (`CROSSDEV`). QEMU is `-M ajit1_generic -cpu AJIT1 -smp 1 -m 128M`. At `nsh>`:

```text
ls /tflite
cat /tflite/README.md
/tflite/hello_world /tflite/inputs/hello_world/0
/tflite/micro_speech /tflite/inputs/micro_speech/yes
/tflite/person_detection /tflite/inputs/person_detection/person
/tflite/resnet50 /tflite/inputs/resnet50/hopper
```

Quit with Ctrl-A, then X. ResNet takes on the order of a minute and a half per picture. The script cap for one ResNet invoke is 700 seconds.

## Scripted tests

From `/home/ajit/ajit-toolchain` inside the container:

```bash
./scripts/test-nuttx-ajit.sh tflite-boot     # 128 MiB image, ls /tflite, hello_world
./scripts/test-nuttx-ajit.sh tflite-small    # hello_world, micro_speech, person_detection
./scripts/test-nuttx-ajit.sh tflite-resnet   # five ResNet top-1 lines, unknown name
./scripts/test-nuttx-ajit.sh tflite          # every input above, then nsh
./scripts/test-nuttx-ajit.sh nsh             # ajit1-qemu:nsh still answers help and hello
```

`tflite-resnet` also runs the generator against a missing `resnet50_int8.tflite` and requires that path in the error. After a `tflite*` test the tree is the tflite config. `nsh` reconfigures `ajit1-qemu:nsh` and checks `_RAM_END` is `0x01100000`.
