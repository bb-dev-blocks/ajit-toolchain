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
export TFLITE_TEST_SRCS="\
tensorflow/lite/micro/examples/micro_speech/micro_speech_test.cc \
gen/ajit_sparc_default_gcc/genfiles/tensorflow/lite/micro/examples/micro_speech/models/micro_speech_quantized_model_data.cc \
gen/ajit_sparc_default_gcc/genfiles/tensorflow/lite/micro/examples/micro_speech/models/audio_preprocessor_int8_model_data.cc \
gen/ajit_sparc_default_gcc/genfiles/tensorflow/lite/micro/examples/micro_speech/testdata/no_1000ms_audio_data.cc \
gen/ajit_sparc_default_gcc/genfiles/tensorflow/lite/micro/examples/micro_speech/testdata/yes_1000ms_audio_data.cc \
gen/ajit_sparc_default_gcc/genfiles/tensorflow/lite/micro/examples/micro_speech/testdata/silence_1000ms_audio_data.cc \
gen/ajit_sparc_default_gcc/genfiles/tensorflow/lite/micro/examples/micro_speech/testdata/noise_1000ms_audio_data.cc \
gen/ajit_sparc_default_gcc/genfiles/tensorflow/lite/micro/examples/micro_speech/testdata/no_30ms_audio_data.cc \
gen/ajit_sparc_default_gcc/genfiles/tensorflow/lite/micro/examples/micro_speech/testdata/yes_30ms_audio_data.cc"
exec "${HERE}/../build_baremetal_qemu.sh" "$@"
