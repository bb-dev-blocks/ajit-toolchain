#!/usr/bin/env bash
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
export TFLITE_GENERATOR_INPUTS="\
tensorflow/lite/micro/models/person_detect.tflite \
tensorflow/lite/micro/examples/person_detection/testdata/person.bmp \
tensorflow/lite/micro/examples/person_detection/testdata/no_person.bmp"
"${HERE}/../ensure_genfiles.sh"
cortos build --target qemu "$@"
