#!/usr/bin/env bash
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
export TFLITE_GENERATOR_INPUTS="\
tensorflow/lite/micro/examples/micro_speech/models/micro_speech_quantized.tflite \
tensorflow/lite/micro/examples/micro_speech/models/audio_preprocessor_int8.tflite \
tensorflow/lite/micro/examples/micro_speech/testdata/no_1000ms.wav \
tensorflow/lite/micro/examples/micro_speech/testdata/yes_1000ms.wav \
tensorflow/lite/micro/examples/micro_speech/testdata/silence_1000ms.wav \
tensorflow/lite/micro/examples/micro_speech/testdata/noise_1000ms.wav \
tensorflow/lite/micro/examples/micro_speech/testdata/no_30ms.wav \
tensorflow/lite/micro/examples/micro_speech/testdata/yes_30ms.wav"
"${HERE}/../ensure_genfiles.sh"
cortos build --target qemu "$@"
