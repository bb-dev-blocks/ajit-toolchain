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
    || grep -q '^CONFIG_SMP=y' .config 2>/dev/null; then
    make distclean >/dev/null 2>&1 || true
    rm -f Make.defs .config .version
    ./tools/configure.sh -E -l -a ../apps ajit1-qemu:nsh
  fi
  make -j"$(nproc)"
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
  "")
    build_one s698pm-dkit:nsh
    build_one s698pm-dkit:smp
    build_one xx3823:nsh
    boot_nsh
    boot_smp
    ;;
  *)
    echo "usage: $0 [leon|nsh|smp]" >&2
    exit 2
    ;;
esac
