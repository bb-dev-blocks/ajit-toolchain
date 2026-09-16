#!/usr/bin/env bash
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
export TFLITE_GENERATOR_INPUTS="\
tensorflow/lite/micro/models/person_detect.tflite \
tensorflow/lite/micro/examples/person_detection/testdata/person.bmp \
tensorflow/lite/micro/examples/person_detection/testdata/no_person.bmp"
export TFLITE_TEST_SRCS="\
tensorflow/lite/micro/examples/person_detection/person_detection_test.cc \
tensorflow/lite/micro/examples/person_detection/model_settings.cc \
gen/ajit_sparc_default_gcc/genfiles/tensorflow/lite/micro/models/person_detect_model_data.cc \
gen/ajit_sparc_default_gcc/genfiles/tensorflow/lite/micro/examples/person_detection/testdata/person_image_data.cc \
gen/ajit_sparc_default_gcc/genfiles/tensorflow/lite/micro/examples/person_detection/testdata/no_person_image_data.cc"
exec "${HERE}/../build_baremetal_qemu.sh" "$@"
