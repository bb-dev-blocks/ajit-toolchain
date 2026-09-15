# AJIT toolchain: Ubuntu 24.04 + Buildroot 2025.02.18 (C-model)

In-tree copy of aparajit `docs/m3-ajit-ubuntu24-buildroot2025-setup-arm64mac.md`. Keep the two files in sync.

How to rebuild the **Ubuntu 24.04 / Buildroot 2025.02.18** stack that compiles SPARC V8 32-bit uClibc (gcc 13.4.0) and runs CoRTOS on the **C simulator** on Apple Silicon (Docker `linux/arm64`).

The 16.04 / Buildroot 2014.08 path is a stepping stone: `docs/m1-ajit-ubuntu16-setup-arm64mac.md`.

Verified on: Darwin + Docker Desktop, host `uname -m` = `arm64`, images `ajit_base:1.0` and `ajit_build_dev:1.0`.

## What “done” means here

Inside `ajit_build_dev`:

- `uname -m` is `aarch64`; `/etc/os-release` `VERSION_ID` is `24.04`.
- Distro `python3` is **3.12** (`/usr/bin/python3`). No python 3.6 PPA.
- After `source ./set_ajit_home` and `source docker/ajit_build/ajit_env`:
  - `command -v sparc-linux-gcc` is `$AJIT_HOME/build/buildroot-2025.02.18/host/bin/sparc-linux-gcc`
  - `sparc-linux-gcc -dumpmachine` prints `sparc-buildroot-linux-uclibc`
  - `sparc-linux-gcc -dumpversion` is `13.4.0`
  - preprocessor: `__sparc_v8__` and `__SIZEOF_POINTER__` 4
- `file` on `$AHIR_RELEASE/lib/libPipeHandlerDebugPthreads.so` is ARM aarch64 (after the AHIR rebuild below). Do not trust the vendored x86 `.so` files in git.
- CoRTOS `example_{001,050,100,150}`: `./build.sh` then `./run.sh`, both exit 0. **`example_250` is not part of this milestone** (C-model hung on 16.04; still M4).

`example_001` prints `CoRTOS:LOG: ... Hello There`. `Thread entered ERROR MODE` on halt is normal.

## Source you need

All product edits live in `repos/ajit-toolchain`. Nested AHIR must be **inside** that clone (`$AJIT_HOME/ahir`) because Darwin `run.sh` bind-mounts only the toolchain repo.

| Piece | Path |
|---|---|
| Toolchain | `repos/ajit-toolchain` (this milestone’s commit on `marshal_updates`) |
| AHIR | `repos/ajit-toolchain/ahir` @ `0816fb6d533715d89364551c267642df701b391c` (`git@github.com:bb-dev-blocks/ahir.git`). Keep the gitlink on this sha, not `master`. |
| Buildroot wrappers | `repos/ajit-toolchain/buildroot_src_2025.02/` (`setup.sh`, `pathsetup.sh`, `ajit_sparc32_uclibc_defconfig`, vendored `buildroot-2025.02.18/`) |
| Parent tarball | `buildroot-2025.02.18.tar.gz` at aparajit root — **extract source only**, do not commit it |
| Vendored x86 drop | `repos/ajit-toolchain/ahir_release/` — leave the committed x86 `.so` in git. Rebuild host libs at setup; do not commit arm64 overlays. |

If the vendored Buildroot tree is missing (fresh clone without that directory):

```bash
mkdir -p repos/ajit-toolchain/buildroot_src_2025.02
tar xf buildroot-2025.02.18.tar.gz -C repos/ajit-toolchain/buildroot_src_2025.02
# results in .../buildroot_src_2025.02/buildroot-2025.02.18/
```

`buildroot_src_2025.02/setup.sh` does **not** open the tarball. Output is `make O=$AJIT_HOME/build/buildroot-2025.02.18`.

Keep `buildroot_src/` (2014.08) on disk; PATH must use 2025.02.18.

Host: Docker Desktop (or equivalent). Do not use aparajit `docker/` or `aparajit-docker` for this flow.

## Build images (host native, no `--platform`)

Scripts that check `pwd` must be run as `./build.sh` / `./run.sh` from their own directory.

```bash
cd repos/ajit-toolchain/docker/ajit_base
./build.sh
# -> ajit_base:1.0   FROM ubuntu:24.04

cd ../ajit_build_dev
./build.sh
# -> ajit_build_dev:1.0
#    uid/gid = host `id -u` / `id -g` (no `getent group docker`)
```

```bash
cd repos/ajit-toolchain/docker/ajit_build_dev
./run.sh          # container name ajit_build_dev
./attach_shell.sh # docker exec -u $(id -nu) -w /home/ajit/ajit-toolchain
```

Inside the container:

```bash
uname -m                    # aarch64
id                          # uid/gid match the host
grep VERSION_ID /etc/os-release   # 24.04
python3 --version           # 3.12.x from /usr/bin/python3
```

Darwin mounts:

- Bind-mount: Mac clone of `ajit-toolchain` → `/home/ajit/ajit-toolchain`.
- Named volume **`ajit-toolchain-build`** → `$AJIT_HOME/build` (Buildroot `O=` output and `BR2_DL_DIR`). `chown` that mount to host uid/gid only (not `…:docker`). Mac gid 20 is Ubuntu `dialout`.
- Case pair on the volume: `touch $AJIT_HOME/build/Foo $AJIT_HOME/build/foo` — both must exist as distinct names.

Linux hosts: bind-mount only (no extra volume).

Do not bake `ajit_build` / `ajit_tools` for this milestone (`FROM ajit_base:1.0` inherits 24.04; not required here).

## Inside the container: env + setup

```bash
source ./set_ajit_home
source docker/ajit_build/ajit_env
./setup.sh
```

`./setup.sh` calls `docker/ajit_build/setup_ajit_build.sh`, which:

1. Runs `buildroot_src_2025.02/setup.sh` (`make defconfig` + `make toolchain` unless gcc already exists under `$O/host/bin`).
2. Runs `scripts/install_ahir_c_libs.sh` (required on arm64).
3. Runs `scripts/ensure_python36.sh` (no-op when distro `python3` is ≥3.6).
4. Builds tools / C-model.

`setup.sh` detects Docker with `/.dockerenv`.

First toolchain build needs network (package downloads into `$AJIT_HOME/build/br-dl`) and **git** on the image (`setup_ajit_base.sh` installs it). Later runs skip `make toolchain` if `sparc-buildroot-linux-uclibc-gcc` is already in `$O/host/bin`.

### SPARC / sysroot

```bash
sparc-linux-gcc -dumpmachine    # sparc-buildroot-linux-uclibc
sparc-linux-gcc -dumpversion    # 13.4.0
```

Short names `sparc-linux-*` are symlinks created by `ajit_env` / `pathsetup.sh` (`AJIT_PROJECT_CROSS_COMPILER=sparc-linux`).

2025 layout (not 2014.08 `host/usr/...`):

- sysroot: `$AJIT_HOME/build/buildroot-2025.02.18/host/sparc-buildroot-linux-uclibc/sysroot`
- libgcc: `$AJIT_HOME/build/buildroot-2025.02.18/host/lib/gcc/sparc-buildroot-linux-uclibc/13.4.0`

`ajit_env` picks those paths when they exist.

gcc 13 defaults to PIE. CoRTOS compile uses `-fno-pic -fno-pie` in `compileToSparcUclibc.py` so the C-model mmap loader sees absolute SPARC code.

### Python

Use distro `python3` (3.12). CoRTOS shebang is `python3`. `ajit_env` does **not** prepend `$AJIT_BUILD_DIR/opt/python-3.6` when `python3` is already ≥3.6.

Python ≥3.10 cannot import vendored `pyelftools-0.25` (`collections.MutableMapping`). `ajit_env` then leaves that tree off `PYTHONPATH` so distro `python3-pyelftools` wins (`setup_ajit_base.sh` installs it).

### AHIR C libs (required on arm64)

Same as M1: vendored `ahir_release/lib/*.so` are x86-64.

```bash
bash "$AJIT_HOME/scripts/install_ahir_c_libs.sh"
file "$AHIR_RELEASE/lib/libPipeHandlerDebugPthreads.so"
# ELF 64-bit LSB shared object, ARM aarch64
```

Do not commit those overlays.

### antlr3c / C-model

Same as M1: aarch64 skips broken `configure`; SConstruct keys off `libantlr3c.a`. `ajit_C_system_model` must be aarch64 ELF. `ajit_debug_monitor` scons may fail; not required for CoRTOS C-model.

**Fake “segfault”:** `signal(SIGTERM, Handle_Segfault)` prints `Error: segmentation fault! giving up!!`. `timeout`/`kill` is SIGTERM.

## CoRTOS C-model

From `$AJIT_HOME` inside the container:

```bash
source ./set_ajit_home
source docker/ajit_build/ajit_env
cd os/rtos/cortos/examples
for e in example_001 example_050 example_100 example_150; do
  echo "======== $e ========"
  rm -rf "$e/cortos_build"
  ( cd "$e" && ./build.sh && ./run.sh )
done
```

C simulator only (`ajit_C_system_model`). Not qemu-ajit, not FPGA.

Always `rm -rf cortos_build` when switching gcc (2014.08 vs 2025). Leftover `main.elf` can make `./run.sh` look green while SPARC compile failed.

`./build.sh` is `cortos build`. SPARC link is `compileToSparcUclibc.py`. `cortos build` now exits non-zero if inner `bash build.sh` fails.

Generated `run_cmodel.sh` **omits `-w` and `-d`**. Restore those flags from the comment in `os/rtos/cortos/src/cortos/files/run_cmodel.sh.tpl` only for debug.

`example_100`: `MAX_LIMIT` is **10**. `cortos_build/` is gitignored.

`example_250`: skip (M4).

Numbered examples do not wait on stdin.

## Do not

- `--platform linux/amd64` on Apple Silicon.
- `getent group docker` / `chown …:docker` on Darwin.
- Commit rebuilt arm64 `ahir_release/**/*.so` (or `.a`) over the x86 drop.
- Commit `buildroot-2025.02.18.tar.gz` or `$AJIT_HOME/build/` / Docker layer caches.
- Point `PATH` at `build/buildroot-2014.08` for this milestone.

## Key files

- `docker/ajit_base/Dockerfile`, `docker/ajit_base/setup_ajit_base.sh`
- `docker/ajit_build_dev/{Dockerfile,build.sh,run.sh,attach_shell.sh}`
- `docker/ajit_build/{ajit_env,setup_ajit_build.sh}` (`ajit_env` is also `$AJIT_HOME/ajit_env`)
- `setup.sh`, `buildroot_src_2025.02/{setup.sh,pathsetup.sh,ajit_sparc32_uclibc_defconfig}`
- `scripts/install_ahir_c_libs.sh`, `scripts/ensure_python36.sh`
- `AjitPublicResources/tools/scripts/compileToSparcUclibc.py`
- `os/rtos/cortos/examples/` — `./build.sh` then `./run.sh`
