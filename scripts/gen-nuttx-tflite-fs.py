#!/usr/bin/env python3
"""Build the /tflite ROMFS: README, input files, and program placeholders.

Models stay in the ELF. This image only holds the files the programs open.
Generated output stays out of git. A missing source path exits non-zero and
prints that path.
"""

import argparse
import struct
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GEN = ROOT / "tflite-micro/gen/ajit_sparc_default_gcc/genfiles"
SRC = ROOT / "os/rtos/cortos2/examples/tflite/resnet50"

README = """\
TFLite on this NuttX image

The four programs are the executables. The model bytes are inside each
executable. You pass an input file. With no argument, or with help, the
program prints usage and does not run.

  /tflite/hello_world <file>
  /tflite/micro_speech <file>
  /tflite/person_detection <file>
  /tflite/resnet50 <file>

Input files live under /tflite/inputs/. One command at a time.
Read this file with: cat /tflite/README.md

The shipped samples are always here. To add your own, put files in
tflite-inputs/ on the build machine and rebuild. A file at
tflite-inputs/resnet50/mypic becomes /tflite/inputs/resnet50/mypic.
The same relative path replaces the shipped sample.
File formats are in docs/tflite-on-nuttx.md.

hello_world
  Text file with one number (x). Prints y near sin(x).
  /tflite/hello_world /tflite/inputs/hello_world/0
  /tflite/hello_world /tflite/inputs/hello_world/1
  /tflite/hello_world /tflite/inputs/hello_world/2
  Those files hold 0, 1.57, and 3.14.

micro_speech
  Raw audio: 16000 big-endian int16 samples, 1000 ms.
  /tflite/micro_speech /tflite/inputs/micro_speech/yes
  /tflite/micro_speech /tflite/inputs/micro_speech/no
  Prints micro_speech: yes or micro_speech: no.

person_detection
  Raw uint8 image, 96x96, 9216 bytes.
  /tflite/person_detection /tflite/inputs/person_detection/person
  /tflite/person_detection /tflite/inputs/person_detection/no_person
  Prints person_detection: person or person_detection: no person.

resnet50
  Raw uint8 image, 224x224x3, 150528 bytes.
  /tflite/resnet50 /tflite/inputs/resnet50/hopper
  /tflite/resnet50 /tflite/inputs/resnet50/tench
  /tflite/resnet50 /tflite/inputs/resnet50/spaniel
  /tflite/resnet50 /tflite/inputs/resnet50/tabby
  /tflite/resnet50 /tflite/inputs/resnet50/panda
  Prints top1: <id> <label>.
  hopper is 457 bow tie. tench is 0 tench.
  spaniel is 217 English springer. tabby is 285 Egyptian cat.
  panda is 388 giant panda.
"""

PLACEHOLDER = b"This program reads an input file. See /tflite/README.md\n"
ALIGN = 16
DIR = 1
FILE = 2
EXEC = 8
MAX_ROMFS = 8 * 1024 * 1024


def die(path: Path) -> None:
    sys.stderr.write(f"tflite fs: missing {path}\n")
    sys.exit(1)


def need(path: Path) -> Path:
    if not path.is_file():
        die(path)
    return path


def parse_c_array(path: Path):
    text = path.read_text()
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end < start:
        die(path)
    vals = []
    for part in text[start + 1 : end].replace("\n", " ").split(","):
        part = part.strip()
        if part:
            vals.append(int(part, 0))
    return vals


def align(n: int) -> int:
    return (n + (ALIGN - 1)) & ~(ALIGN - 1)


def checksum(blob: bytes) -> int:
    total = 0
    if len(blob) % 4:
        blob += b"\0" * (4 - (len(blob) % 4))
    for i in range(0, len(blob), 4):
        total = (total + struct.unpack(">I", blob[i : i + 4])[0]) & 0xFFFFFFFF
    return total


class Node:
    def __init__(self, name, kind, data=b"", exe=False):
        self.name = name
        self.kind = kind
        self.data = data
        self.exe = exe
        self.children = []
        self.link = None
        self.offset = 0
        self.next_off = 0

    def header_len(self) -> int:
        return align(16 + len(self.name.encode()) + 1)


def add_dir(name, parent):
    node = Node(name, "dir", exe=True)
    dot = Node(".", "link")
    dotdot = Node("..", "link")
    dot.link = node
    dotdot.link = parent
    node.children = [dot, dotdot]
    return node


def layout(nodes, cursor):
    for node in nodes:
        node.offset = cursor
        span = node.header_len()
        if node.kind == "file":
            span += len(node.data)
        cursor = align(node.offset + span)
        if node.kind == "dir":
            cursor = layout(node.children, cursor)
    for i, node in enumerate(nodes):
        node.next_off = nodes[i + 1].offset if i + 1 < len(nodes) else 0
    return cursor


def emit_header(node, info):
    if node.kind == "link":
        mode = 0
    elif node.kind == "dir":
        mode = DIR | EXEC
    else:
        mode = FILE | (EXEC if node.exe else 0)
    name = node.name.encode() + b"\0"
    buf = bytearray(16 + align(len(name)))
    struct.pack_into(">I", buf, 0, (node.next_off & ~15) | mode)
    struct.pack_into(">I", buf, 4, info)
    struct.pack_into(">I", buf, 8, len(node.data) if node.kind == "file" else 0)
    buf[16 : 16 + len(name)] = name
    struct.pack_into(">I", buf, 12, (-checksum(bytes(buf))) & 0xFFFFFFFF)
    return bytes(buf)


def write_node(img, node, root):
    if node.kind == "link":
        info = node.link.offset
    elif node.kind == "dir":
        info = node.offset if node is root else node.children[0].offset
    else:
        info = 0
    hdr = emit_header(node, info)
    img[node.offset : node.offset + len(hdr)] = hdr
    if node.kind == "file" and node.data:
        at = node.offset + len(hdr)
        img[at : at + len(node.data)] = node.data
    if node.kind == "dir":
        for child in node.children:
            write_node(img, child, root)


def build_romfs(files) -> bytes:
    """files: list of (path, data, executable). path is relative, no leading slash."""
    root = Node(".", "dir", exe=True)
    dotdot = Node("..", "link")
    dotdot.link = root
    root.children = [dotdot]

    def ensure_dir(parts):
        node = root
        for part in parts:
            found = None
            for child in node.children:
                if child.name == part and child.kind == "dir":
                    found = child
                    break
            if found is None:
                found = add_dir(part, node)
                node.children.append(found)
            node = found
        return node

    for path, data, exe in files:
        parts = path.split("/")
        parent = root if len(parts) == 1 else ensure_dir(parts[:-1])
        parent.children.append(Node(parts[-1], "file", data, exe))

    start = align(16 + len(b"tflite\0"))
    root.offset = start
    cursor = layout(root.children, align(start + root.header_len()))
    root.next_off = root.children[0].offset
    end = align(cursor)
    end = (end + 511) & ~511
    img = bytearray(end)
    img[0:8] = b"-rom1fs-"
    struct.pack_into(">I", img, 8, end)
    img[16 : 16 + 7] = b"tflite\0"
    write_node(img, root, root)
    struct.pack_into(">I", img, 12, (-checksum(bytes(img[:512]))) & 0xFFFFFFFF)
    check_romfs(bytes(img), root.offset, files)
    return bytes(img)


def name_of(img, off):
    raw = img[off + 16 :]
    return raw[: raw.find(b"\0")].decode()


def walk(img, off):
    seen = set()
    while off and off not in seen:
        seen.add(off)
        yield off
        off = struct.unpack_from(">I", img, off)[0] & ~15


def find_from(img, start, part):
    for off in walk(img, start):
        if name_of(img, off) != part:
            continue
        nxt = struct.unpack_from(">I", img, off)[0]
        mode = nxt & 7
        info = struct.unpack_from(">I", img, off + 4)[0]
        if mode == 0:
            target = info
            tmode = struct.unpack_from(">I", img, target)[0] & 7
            tinfo = struct.unpack_from(">I", img, target + 4)[0]
            return tinfo if tmode == 1 else target
        if mode == 1:
            return info
        return off
    raise SystemExit(f"tflite fs: romfs missing {part}")


def lookup(img, root, path):
    off = root
    for part in path.split("/"):
        if part:
            off = find_from(img, off, part)
    return off


def file_bytes(img, off):
    size = struct.unpack_from(">I", img, off + 8)[0]
    at = align(off + 16 + len(name_of(img, off)) + 1)
    return img[at : at + size]


def check_romfs(img, root, files):
    for path, data, exe in files:
        off = lookup(img, root, path)
        got = file_bytes(img, off)
        if got != data:
            raise SystemExit(f"tflite fs: romfs mismatch {path}")
        if exe and (struct.unpack_from(">I", img, off)[0] & EXEC) == 0:
            raise SystemExit(f"tflite fs: {path} is not executable")


def objcopy_romfs(blob: bytes, out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    (out / "romfs.img").write_bytes(blob)
    subprocess.check_call(
        [
            "sparc-linux-objcopy",
            "-I",
            "binary",
            "-O",
            "elf32-sparc",
            "-B",
            "sparc",
            "--rename-section",
            ".data=.rodata,alloc,load,readonly,data,contents",
            "romfs.img",
            "romfs.o",
        ],
        cwd=out,
    )
    subprocess.check_call(
        ["sparc-linux-ar", "rcs", "libromfs.a", "romfs.o"], cwd=out
    )


def load_extra(folder: Path):
    """Copy of tflite-inputs/, mapped under inputs/ on the volume."""
    if not folder.is_dir():
        return []
    found = []
    for path in sorted(folder.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(folder)
        if any(part.startswith(".") for part in rel.parts):
            continue
        found.append((f"inputs/{rel.as_posix()}", path.read_bytes()))
    return found


def merge_files(stock, extra):
    merged = {}
    order = []
    for path, data, exe in stock:
        if path not in merged:
            order.append(path)
        merged[path] = (data, exe)
    for path, data in extra:
        if path not in merged:
            order.append(path)
            print(f"tflite fs: add {path}")
        else:
            print(f"tflite fs: replace {path}")
        merged[path] = (data, False)
    return [(path, merged[path][0], merged[path][1]) for path in order]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    parser.add_argument("--inputs", default=str(ROOT / "tflite-inputs"))
    args = parser.parse_args()

    yes_cc = need(
        GEN
        / "tensorflow/lite/micro/examples/micro_speech/testdata/yes_1000ms_audio_data.cc"
    )
    no_cc = need(
        GEN
        / "tensorflow/lite/micro/examples/micro_speech/testdata/no_1000ms_audio_data.cc"
    )
    person_cc = need(
        GEN
        / "tensorflow/lite/micro/examples/person_detection/testdata/person_image_data.cc"
    )
    no_person_cc = need(
        GEN
        / "tensorflow/lite/micro/examples/person_detection/testdata/no_person_image_data.cc"
    )
    yes = parse_c_array(yes_cc)
    no = parse_c_array(no_cc)
    if len(yes) != 16000 or len(no) != 16000:
        die(yes_cc)
    person = parse_c_array(person_cc)
    no_person = parse_c_array(no_person_cc)
    if len(person) != 9216 or len(no_person) != 9216:
        die(person_cc)
    if any(v < 0 or v > 255 for v in person + no_person):
        die(person_cc)

    sys.path.insert(0, str(SRC))
    from preprocess import jpeg_to_bytes, load_spec

    spec = load_spec(need(SRC / "inputs" / "preprocess_spec.json"))
    order = need(SRC / "inputs" / "order.txt")
    images = []
    for line in order.read_text().splitlines():
        name = line.strip()
        if not name or name.startswith("#"):
            continue
        jpeg = need(SRC / "inputs" / f"{name}.jpg")
        raw = jpeg_to_bytes(jpeg, spec)
        if len(raw) != 224 * 224 * 3:
            die(jpeg)
        images.append((name, raw))
    if len(images) != 5:
        die(order)

    files = [
        ("README.md", README.encode(), False),
        ("hello_world", PLACEHOLDER, True),
        ("micro_speech", PLACEHOLDER, True),
        ("person_detection", PLACEHOLDER, True),
        ("resnet50", PLACEHOLDER, True),
        ("inputs/hello_world/0", b"0\n", False),
        ("inputs/hello_world/1", b"1.57\n", False),
        ("inputs/hello_world/2", b"3.14\n", False),
        ("inputs/micro_speech/yes", struct.pack(">" + "h" * len(yes), *yes), False),
        ("inputs/micro_speech/no", struct.pack(">" + "h" * len(no), *no), False),
        ("inputs/person_detection/person", bytes(person), False),
        ("inputs/person_detection/no_person", bytes(no_person), False),
    ]
    for name, raw in images:
        files.append((f"inputs/resnet50/{name}", raw, False))

    files = merge_files(files, load_extra(Path(args.inputs)))
    blob = build_romfs(files)
    if len(blob) > MAX_ROMFS:
        sys.stderr.write(
            f"tflite fs: /tflite volume is {len(blob)} bytes;"
            f" limit is {MAX_ROMFS}\n"
        )
        sys.exit(1)
    objcopy_romfs(blob, Path(args.out))
    print(f"tflite fs: {len(files)} files, {len(blob)} bytes")


if __name__ == "__main__":
    main()
