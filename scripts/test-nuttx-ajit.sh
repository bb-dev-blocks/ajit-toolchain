#!/usr/bin/env bash
# Cross-compile NuttX SPARC configs with the toolchain's sparc-linux-gcc.
set -eo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if ! command -v sparc-linux-gcc >/dev/null 2>&1; then
  # shellcheck disable=SC1091
  source ./set_ajit_home
  # shellcheck disable=SC1091
  source docker/ajit_build/ajit_env
fi

export CROSSDEV=sparc-linux-

build_one() {
  local cfg="$1"
  echo "===== ${cfg} ====="
  cd "$ROOT/nuttx"
  make distclean >/dev/null 2>&1 || true
  rm -f Make.defs .config .version
  ./tools/configure.sh -E -l -a ../apps "$cfg"
  make -j"$(nproc)"
  file nuttx | grep -q "ELF 32-bit MSB"
  echo "OK ${cfg}"
}

boot_nsh() {
  cd "$ROOT/nuttx"
  if ! grep -q '^CONFIG_ARCH_BOARD_AJIT1_QEMU=y' .config 2>/dev/null \
    || grep -q '^CONFIG_SMP=y' .config 2>/dev/null \
    || grep -q '^CONFIG_AJIT1_QEMU_TFLITE=y' .config 2>/dev/null; then
    make distclean >/dev/null 2>&1 || true
    rm -f Make.defs .config .version
    ./tools/configure.sh -E -l -a ../apps ajit1-qemu:nsh
  fi
  make -j"$(nproc)"
  sparc-linux-nm nuttx > nuttx.nm
  grep -q '01100000 A _RAM_END' nuttx.nm
  rm -f nuttx.nm
  python3 - "$ROOT" <<'PY'
import os, socket, subprocess, sys, time

root = sys.argv[1]
kernel = os.path.join(root, "nuttx", "nuttx")
sock = socket.socket()
sock.bind(("127.0.0.1", 0))
port = sock.getsockname()[1]
sock.close()
cmd = [
    "qemu-system-sparc", "-M", "ajit1_generic", "-cpu", "AJIT1",
    "-smp", "1", "-m", "128M", "-display", "none", "-monitor", "none",
    "-nographic", "-serial", f"tcp:127.0.0.1:{port},server=on",
    "-kernel", kernel,
]
proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
s = None
try:
    for _ in range(50):
        try:
            s = socket.create_connection(("127.0.0.1", port), timeout=0.2)
            break
        except OSError:
            if proc.poll() is not None:
                break
            time.sleep(0.1)
    if s is None:
        sys.stderr.write(proc.stderr.read().decode("latin1", "replace"))
        sys.exit(1)
    s.settimeout(0.3)

    def read_until(pred, seconds):
        buf = b""
        end = time.time() + seconds
        while time.time() < end and not pred(buf):
            try:
                chunk = s.recv(4096)
            except socket.timeout:
                continue
            if not chunk:
                break
            buf += chunk
        return buf

    boot = read_until(lambda b: b"nsh>" in b, 15)
    s.sendall(b"help\n")
    helped = read_until(
        lambda b: b"Builtin Apps" in b and b.rfind(b"nsh>") > b.find(b"Builtin Apps"),
        10)
    s.sendall(b"hello\n")
    hello = read_until(lambda b: b"Hello, World!!" in b, 10)
    text = (boot + helped + hello).decode("latin1", "replace")
    sys.stdout.write(text)
    if b"nsh>" not in boot or b"Builtin Apps" not in helped or b"Hello, World!!" not in hello:
        sys.exit(1)
    print("OK ajit1-qemu:nsh")
finally:
    if s is not None:
        s.close()
    proc.terminate()
    try:
        proc.wait(timeout=2)
    except subprocess.TimeoutExpired:
        proc.kill()
PY
}

boot_smp() {
  cd "$ROOT/nuttx"
  if ! grep -q '^CONFIG_ARCH_BOARD_AJIT1_QEMU=y' .config 2>/dev/null \
    || ! grep -q '^CONFIG_SMP=y' .config 2>/dev/null; then
    make distclean >/dev/null 2>&1 || true
    rm -f Make.defs .config .version
    ./tools/configure.sh -E -l -a ../apps ajit1-qemu:smp
  fi
  make -j"$(nproc)"
  python3 - "$ROOT" <<'PY'
import os, socket, subprocess, sys, time

root = sys.argv[1]
kernel = os.path.join(root, "nuttx", "nuttx")

def boot(smp, send_ps):
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    cmd = [
        "qemu-system-sparc", "-M", "ajit1_generic", "-cpu", "AJIT1",
        "-smp", str(smp), "-m", "128M", "-display", "none", "-monitor", "none",
        "-nographic", "-serial", f"tcp:127.0.0.1:{port},server=on",
        "-kernel", kernel,
    ]
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    s = None
    try:
        for _ in range(50):
            try:
                s = socket.create_connection(("127.0.0.1", port), timeout=0.2)
                break
            except OSError:
                if proc.poll() is not None:
                    break
                time.sleep(0.1)
        if s is None:
            sys.stderr.write(proc.stderr.read().decode("latin1", "replace"))
            sys.exit(1)
        s.settimeout(0.3)

        def read_until(pred, seconds):
            buf = b""
            end = time.time() + seconds
            while time.time() < end and not pred(buf):
                try:
                    chunk = s.recv(4096)
                except socket.timeout:
                    continue
                if not chunk:
                    break
                buf += chunk
            return buf

        bootbuf = read_until(lambda b: b"nsh>" in b or b"Assertion failed" in b, 15)
        psbuf = b""
        if send_ps and b"nsh>" in bootbuf:
            s.sendall(b"ps\n")
            psbuf = read_until(lambda b: b"nsh_main" in b and b.rfind(b"nsh>") > b.find(b"nsh_main"), 10)
        text = (bootbuf + psbuf).decode("latin1", "replace")
        sys.stdout.write(text)
        need = [b"nsh>"] + [f"CPU{n} online".encode() for n in range(1, smp)]
        if any(item not in bootbuf for item in need) or (send_ps and b"nsh_main" not in psbuf):
            sys.exit(1)
        print(f"OK ajit1-qemu:smp -smp {smp}")
    finally:
        if s is not None:
            s.close()
        proc.terminate()
        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            proc.kill()

boot(2, True)
boot(4, False)
PY
}

build_tflite() {
  grep -q '_RAM_SIZE = 16M;' "$ROOT/nuttx/boards/sparc/ajit1/ajit1-qemu/scripts/linksparc.ld"
  grep -q 'ram  (rw!x) : ORIGIN = 0x00100000, LENGTH = 16M' \
    "$ROOT/nuttx/boards/sparc/ajit1/ajit1-qemu/scripts/linksparc.ld"
  grep -q '_RAM_SIZE = 128M;' "$ROOT/nuttx/boards/sparc/ajit1/ajit1-qemu/scripts/linksparc-128m.ld"
  grep -q 'ram  (rw!x) : ORIGIN = 0x00100000, LENGTH = 128M' \
    "$ROOT/nuttx/boards/sparc/ajit1/ajit1-qemu/scripts/linksparc-128m.ld"
  grep -q '^CONFIG_RAM_SIZE=16777216$' \
    "$ROOT/nuttx/boards/sparc/ajit1/ajit1-qemu/configs/nsh/defconfig"
  grep -q '^CONFIG_RAM_SIZE=134217728$' \
    "$ROOT/nuttx/boards/sparc/ajit1/ajit1-qemu/configs/tflite/defconfig"

  cd "$ROOT/nuttx"
  make distclean >/dev/null 2>&1 || true
  rm -f Make.defs .config .version
  ./tools/configure.sh -E -l -a ../apps ajit1-qemu:tflite
  grep -q '^CONFIG_RAM_SIZE=134217728$' .config
  grep -q '^CONFIG_AJIT1_QEMU_TFLITE=y$' .config
  make -j"$(nproc)"
  # 0x00100000 + 128 MiB. The 16 MiB script ends at 0x01100000.
  # Write the map to a file: grep -q closes a pipe early and pipefail
  # then treats nm's SIGPIPE as failure.
  sparc-linux-nm nuttx > nuttx.nm
  grep -q '08100000 A _RAM_END' nuttx.nm
  rm -f nuttx.nm
  file nuttx | grep -q "ELF 32-bit MSB"
}

run_tflite_qemu() {
  python3 - "$ROOT" "$1" <<'PY'
import math, os, re, socket, subprocess, sys, time

root = sys.argv[1]
level = sys.argv[2]
kernel = os.path.join(root, "nuttx", "nuttx")
sock = socket.socket()
sock.bind(("127.0.0.1", 0))
port = sock.getsockname()[1]
sock.close()
cmd = [
    "qemu-system-sparc", "-M", "ajit1_generic", "-cpu", "AJIT1",
    "-smp", "1", "-m", "128M", "-display", "none", "-monitor", "none",
    "-nographic", "-serial", f"tcp:127.0.0.1:{port},server=on",
    "-kernel", kernel,
]
proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
s = None
try:
    for _ in range(50):
        try:
            s = socket.create_connection(("127.0.0.1", port), timeout=0.2)
            break
        except OSError:
            if proc.poll() is not None:
                break
            time.sleep(0.1)
    if s is None:
        sys.stderr.write(proc.stderr.read().decode("latin1", "replace"))
        sys.exit(1)
    s.settimeout(0.3)

    def read_until(pred, seconds):
        buf = b""
        end = time.time() + seconds
        while time.time() < end and not pred(buf):
            try:
                chunk = s.recv(4096)
            except socket.timeout:
                continue
            if not chunk:
                break
            buf += chunk
        return buf

    chunks = []

    def fail(msg, buf):
        sys.stdout.write(b"".join(chunks + [buf]).decode("latin1", "replace"))
        sys.stderr.write(msg + "\n")
        sys.exit(1)

    boot = read_until(lambda b: b"nsh>" in b, 15)
    chunks.append(boot)
    if b"nsh>" not in boot:
        fail("boot did not reach nsh>", b"")

    s.sendall(b"ls /tflite\n")
    listed = read_until(
        lambda b: b.rfind(b"nsh>") > b.find(b"/tflite"), 10)
    chunks.append(listed)
    for name in (b"hello_world", b"micro_speech", b"person_detection", b"resnet50"):
        if name not in listed:
            fail("ls /tflite missing " + name.decode(), b"")

    s.sendall(b"cat /tflite/README.md\n")
    readme = read_until(
        lambda b: b"Input files live under /tflite/inputs/" in b
        and b.rfind(b"nsh>") > b.find(b"Input files"),
        10)
    chunks.append(readme)
    if b"Input files live under /tflite/inputs/" not in readme:
        fail("cat /tflite/README.md missing the how-to", b"")

    if level != "resnet":
        s.sendall(b"hello_world 0\n")
        bare = read_until(lambda b: b.rfind(b"nsh>") > 0, 10)
        chunks.append(bare)
        if b"hello_world: x=" in bare:
            fail("bare hello_world ran", b"")

    if level != "resnet":
        shown = {"0": ("0", 0.0), "1": ("1.57", 1.57), "2": ("3.14", 3.14)}
        for token, (label, x) in shown.items():
            s.sendall(
                ("/tflite/hello_world /tflite/inputs/hello_world/%s\n" % token).encode()
            )
            out = read_until(
                lambda b, label=label: ("hello_world: x=%s y=" % label).encode() in b
                and b.rfind(b"nsh>") > b.find(b"hello_world: x="),
                60)
            chunks.append(out)
            text = out.decode("latin1", "replace")
            match = re.search(r"hello_world: x=([0-9.]+) y=([+-]?[0-9.]+)", text)
            if match is None or match.group(1) != label:
                fail("missing pass line for %s" % token, b"")
            y = float(match.group(2))
            if abs(y - math.sin(x)) > 0.05:
                fail("y=%s off sin(%s)" % (y, x), b"")

        s.sendall(b"/tflite/hello_world nope\n")
        bad = read_until(
            lambda b: b"usage:" in b and b.rfind(b"nsh>") > b.find(b"usage:"), 10)
        chunks.append(bad)
        if b"hello_world: x=" in bad:
            fail("unknown input still ran inference", b"")

    if level == "small" or level == "e2e":
        for token, label in (("yes", "yes"), ("no", "no")):
            s.sendall(
                ("/tflite/micro_speech /tflite/inputs/micro_speech/%s\n" % token).encode()
            )
            out = read_until(
                lambda b, label=label: ("micro_speech: %s" % label).encode() in b
                and b.rfind(b"nsh>") > b.find(b"micro_speech:"),
                600)
            chunks.append(out)
            if ("micro_speech: %s" % label).encode() not in out:
                fail("missing micro_speech pass line for %s" % token, b"")
        s.sendall(b"/tflite/micro_speech nope\n")
        bad = read_until(
            lambda b: b"usage:" in b and b.rfind(b"nsh>") > b.find(b"usage:"), 10)
        chunks.append(bad)
        if b"micro_speech: yes" in bad or b"micro_speech: no" in bad:
            fail("unknown micro_speech input still ran inference", b"")

        for token, label in (("person", "person"), ("no_person", "no person")):
            s.sendall(
                (
                    "/tflite/person_detection /tflite/inputs/person_detection/%s\n"
                    % token
                ).encode()
            )
            out = read_until(
                lambda b, label=label: ("person_detection: %s" % label).encode() in b
                and b.rfind(b"nsh>") > b.find(b"person_detection:"),
                300)
            chunks.append(out)
            if ("person_detection: %s" % label).encode() not in out:
                fail("missing person_detection pass line for %s" % token, b"")
        s.sendall(b"/tflite/person_detection nope\n")
        bad = read_until(
            lambda b: b"usage:" in b and b.rfind(b"nsh>") > b.find(b"usage:"), 10)
        chunks.append(bad)
        if b"person_detection: person" in bad or b"person_detection: no person" in bad:
            fail("unknown person_detection input still ran inference", b"")

    if level == "resnet" or level == "e2e":
        expected = (
            ("hopper", "top1: 457 bow tie"),
            ("tench", "top1: 0 tench"),
            ("spaniel", "top1: 217 English springer"),
            ("tabby", "top1: 285 Egyptian cat"),
            ("panda", "top1: 388 giant panda"),
        )
        for token, label in expected:
            s.sendall(
                ("/tflite/resnet50 /tflite/inputs/resnet50/%s\n" % token).encode()
            )
            out = read_until(
                lambda b, label=label: label.encode() in b
                and b.rfind(b"nsh>") > b.find(b"top1:"),
                700)
            chunks.append(out)
            if label.encode() not in out:
                fail("missing resnet50 pass line for %s" % token, b"")
        s.sendall(b"/tflite/resnet50 nope\n")
        bad = read_until(
            lambda b: b"usage:" in b and b.rfind(b"nsh>") > b.find(b"usage:"), 10)
        chunks.append(bad)
        if b"top1:" in bad:
            fail("unknown resnet50 input still ran inference", b"")

    sys.stdout.write(b"".join(chunks).decode("latin1", "replace"))
    print("OK ajit1-qemu:tflite")
finally:
    if s is not None:
        s.close()
    proc.terminate()
    try:
        proc.wait(timeout=2)
    except subprocess.TimeoutExpired:
        proc.kill()
PY
}

boot_tflite() {
  build_tflite
  run_tflite_qemu boot
}

boot_tflite_small() {
  build_tflite
  run_tflite_qemu small
}

check_resnet_missing() {
  local missing="/tmp/resnet50_int8.tflite"
  local err
  rm -f "$missing"
  if err=$(python3 "$ROOT/scripts/gen-nuttx-resnet50.py" \
      --model "$missing" --out /tmp/resnet-missing-test 2>&1); then
    echo "missing resnet50 model should fail the build" >&2
    exit 1
  fi
  printf '%s\n' "$err" | grep -q "resnet50_int8.tflite"
}

boot_tflite_resnet() {
  check_resnet_missing
  build_tflite
  run_tflite_qemu resnet
}

boot_tflite_e2e() {
  test -f "$ROOT/docs/tflite-on-nuttx.md"
  grep -q '/tflite/hello_world' "$ROOT/docs/tflite-on-nuttx.md"
  grep -q '/tflite/README.md' "$ROOT/docs/tflite-on-nuttx.md"
  grep -q '/tflite/inputs/' "$ROOT/docs/tflite-on-nuttx.md"
  grep -q 'tflite-inputs/' "$ROOT/docs/tflite-on-nuttx.md"
  grep -q '224' "$ROOT/docs/tflite-on-nuttx.md"
  grep -q 'tflite-small' "$ROOT/docs/tflite-on-nuttx.md"
  grep -q 'tflite-resnet' "$ROOT/docs/tflite-on-nuttx.md"
  grep -q 'ajit1-qemu:tflite' "$ROOT/docs/tflite-on-nuttx.md"
  check_resnet_missing
  build_tflite
  run_tflite_qemu e2e
  boot_nsh
}

mode="${1:-}"
case "$mode" in
  leon)
    build_one s698pm-dkit:nsh
    build_one s698pm-dkit:smp
    build_one xx3823:nsh
    ;;
  nsh)
    boot_nsh
    ;;
  smp)
    boot_smp
    ;;
  tflite-boot)
    boot_tflite
    ;;
  tflite-small)
    boot_tflite_small
    ;;
  tflite-resnet)
    boot_tflite_resnet
    ;;
  tflite)
    boot_tflite_e2e
    ;;
  "")
    build_one s698pm-dkit:nsh
    build_one s698pm-dkit:smp
    build_one xx3823:nsh
    boot_nsh
    boot_smp
    ;;
  *)
    echo "usage: $0 [leon|nsh|smp|tflite-boot|tflite-small|tflite-resnet|tflite]" >&2
    exit 2
    ;;
esac
