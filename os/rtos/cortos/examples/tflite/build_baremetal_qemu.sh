#!/usr/bin/env bash
# Build a TFLite Micro test ELF for qemu-ajit (no CoRTOS).
# Caller sets TFLITE_TEST_SRCS (space-separated .cc paths, abs or vs $TFLM).

set -euo pipefail

if [[ -z "${AJIT_HOME:-}" ]]; then
  echo "tflite: set AJIT_HOME (source set_ajit_home)" >&2
  exit 1
fi

TFLITE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TFLM="${AJIT_HOME}/tflite-micro"
GEN="${TFLM}/gen/ajit_sparc_default_gcc"
LIB="${GEN}/lib/libtensorflow-microlite.a"
DL="${TFLM}/tensorflow/lite/micro/tools/make/downloads"
OUT="$(pwd)/baremetal_qemu"
TRAPS="${AJIT_HOME}/os/rtos/cortos/src/cortos/files/build_asms/trap_handlers.s.tpl"

if [[ -z "${TFLITE_TEST_SRCS:-}" ]]; then
  echo "tflite: TFLITE_TEST_SRCS is empty" >&2
  exit 1
fi

if [[ ! -f "$LIB" ]]; then
  echo "tflite: building libtensorflow-microlite.a"
  make -C "$TFLM" -f tensorflow/lite/micro/tools/make/Makefile \
    TARGET=ajit TARGET_ARCH=sparc microlite
fi

if [[ -n "${TFLITE_GENERATOR_INPUTS:-}" ]]; then
  echo "tflite: generating cc arrays"
  (cd "$TFLM" && python3 tensorflow/lite/micro/tools/generate_cc_arrays.py \
    "${GEN}/genfiles/" $TFLITE_GENERATOR_INPUTS)
fi

mkdir -p "$OUT"

CXXFLAGS=(
  -fno-pic -fno-pie
  -m32 -mcpu=v8 -std=c++17
  -fno-rtti -fno-exceptions -fno-threadsafe-statics -fno-use-cxa-atexit
  -fpermissive -fno-builtin-printf -funsigned-char
  -fno-delete-null-pointer-checks -fomit-frame-pointer
  -ffunction-sections -fdata-sections
  -DTF_LITE_STATIC_MEMORY -DTF_LITE_DISABLE_X86_NEON
  -DTF_LITE_MCU_DEBUG_LOG
  -DTF_LITE_USE_GLOBAL_CMATH_FUNCTIONS
  -DTF_LITE_USE_GLOBAL_MIN -DTF_LITE_USE_GLOBAL_MAX
  -I"$TFLM"
  -I"${GEN}/genfiles"
  -I"$DL"
  -I"$DL/gemmlowp"
  -I"$DL/flatbuffers/include"
  -I"$DL/kissfft"
  -I"$DL/ruy"
  -I"$AJIT_UCLIBC_HEADERS_DIR"
)

OBJS=()
i=0
for src in $TFLITE_TEST_SRCS; do
  if [[ "$src" != /* ]]; then
    src="${TFLM}/${src}"
  fi
  obj="${OUT}/src_${i}.o"
  sparc-linux-g++ -c "${CXXFLAGS[@]}" "$src" -o "$obj"
  OBJS+=("$obj")
  i=$((i + 1))
done

sparc-linux-g++ -c "${CXXFLAGS[@]}" "${TFLITE_DIR}/cxxstub.cc" -o "${OUT}/cxxstub.o"

sparc-linux-gcc -m32 -mcpu=v8 -fno-pic -fno-pie -c "${TFLITE_DIR}/crt0.S" -o "${OUT}/crt0.o"
cp "$TRAPS" "${OUT}/trap_handlers.s"
sparc-linux-gcc -m32 -mcpu=v8 -fno-pic -fno-pie -c "${OUT}/trap_handlers.s" -o "${OUT}/trap_handlers.o"

UCLIBC_LIB="${AJIT_UCLIBC_LIB_DIR}"
LIBGCC="${AJIT_LIBGCC_INSTALL_DIR}"

sparc-linux-ld \
  -T "${TFLITE_DIR}/LinkerScript.qemu.txt" \
  -e _start \
  -o "${OUT}/main.elf" \
  "${OUT}/crt0.o" \
  "${OUT}/trap_handlers.o" \
  "${OUT}/cxxstub.o" \
  "${OBJS[@]}" \
  "$LIB" \
  -L"$UCLIBC_LIB" \
  ${LIBGCC:+-L"$LIBGCC"} \
  -static --gc-sections \
  -lm -lc -lgcc \
  -lm -lc -lgcc

echo "tflite: wrote ${OUT}/main.elf"
