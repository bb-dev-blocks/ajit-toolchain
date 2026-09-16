#!/usr/bin/env bash
# Shared ExtraCc list for a kernel example dir (basename is the kernel name).

tflite_kernel_srcs() {
  local k
  k="$(basename "$(pwd)")"
  case "$k" in
    conv)
      printf '%s' "\
tensorflow/lite/micro/kernels/conv_test.cc \
tensorflow/lite/micro/kernels/conv_test_common.cc \
tensorflow/lite/micro/kernels/testdata/conv_test_data.cc"
      ;;
    *)
      printf '%s' "tensorflow/lite/micro/kernels/${k}_test.cc"
      ;;
  esac
}

tflite_kernel_extra_cc_yaml() {
  local src
  for src in $(tflite_kernel_srcs); do
    printf '  - tflite-micro/%s\n' "$src"
  done
  printf '  - os/rtos/cortos/examples/tflite/cxxstub.cc\n'
}
