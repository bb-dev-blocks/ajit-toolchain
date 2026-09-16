// CoRTOS + TFLM ResNet-50 ImageNet demo. Verbose UART; pass strings come
// from expected_uart.txt (invoke ok + top-1).

#include <cstdint>
#include <cstdio>
#include <cstring>

#include "input_data.h"
#include "labels.h"
#include "model_blob.h"
#include "tensorflow/lite/micro/micro_interpreter.h"
#include "tensorflow/lite/micro/micro_log.h"
#include "tensorflow/lite/micro/micro_mutable_op_resolver.h"
#include "tensorflow/lite/micro/micro_time.h"
#include "tensorflow/lite/micro/system_setup.h"
#include "tensorflow/lite/schema/schema_generated.h"

namespace {

constexpr int kTensorArenaSize = 64 * 1024 * 1024;
alignas(16) uint8_t tensor_arena[kTensorArenaSize];

const char* TypeName(TfLiteType t) {
  switch (t) {
    case kTfLiteFloat32:
      return "float32";
    case kTfLiteInt8:
      return "int8";
    case kTfLiteUInt8:
      return "uint8";
    case kTfLiteInt32:
      return "int32";
    case kTfLiteInt64:
      return "int64";
    default:
      return "other";
  }
}

void PrintTensor(const char* tag, const TfLiteTensor* t) {
  if (t == nullptr) {
    MicroPrintf("%s: null", tag);
    return;
  }
  char dims[64] = "(none)";
  if (t->dims != nullptr && t->dims->size > 0) {
    int n = 0;
    dims[0] = '\0';
    for (int i = 0; i < t->dims->size && n < 60; ++i) {
      n += snprintf(dims + n, sizeof(dims) - static_cast<size_t>(n), "%s%d",
                    i ? "x" : "", t->dims->data[i]);
    }
  }
  MicroPrintf("%s: type=%s bytes=%d scale=%f zp=%d dims=%s", tag,
              TypeName(t->type), static_cast<int>(t->bytes),
              static_cast<double>(t->params.scale), t->params.zero_point, dims);
}

float Dequant(const TfLiteTensor* t, int i) {
  if (t->type == kTfLiteFloat32) {
    return t->data.f[i];
  }
  if (t->type == kTfLiteInt8) {
    return (static_cast<int>(t->data.int8[i]) - t->params.zero_point) *
           t->params.scale;
  }
  if (t->type == kTfLiteUInt8) {
    return (static_cast<int>(t->data.uint8[i]) - t->params.zero_point) *
           t->params.scale;
  }
  return 0.0f;
}

int NumClasses(const TfLiteTensor* t) {
  if (t == nullptr || t->dims == nullptr || t->dims->size < 1) {
    return 0;
  }
  return t->dims->data[t->dims->size - 1];
}

const char* Label(int idx) {
  if (idx < 0 || idx >= kLabelCount) {
    return "?";
  }
  return kLabels[idx];
}

}  // namespace

extern "C" int main(int argc, char** argv) {
  (void)argc;
  (void)argv;
  tflite::InitializeTarget();

  const uint8_t* model_data = _binary_model_tflite_start;
  const int model_size =
      static_cast<int>(_binary_model_tflite_end - _binary_model_tflite_start);
  MicroPrintf("resnet50: model_bytes=%d arena_bytes=%d input_bytes=%d labels=%d\n",
              model_size, kTensorArenaSize, g_input_image_data_size, kLabelCount);

  MicroPrintf("resnet50: GetModel\n");
  const tflite::Model* model = tflite::GetModel(model_data);
  if (model->version() != TFLITE_SCHEMA_VERSION) {
    MicroPrintf("resnet50: schema %d != %d\n", model->version(),
                TFLITE_SCHEMA_VERSION);
    return 1;
  }
  MicroPrintf("resnet50: schema ok version=%d\n", model->version());

  tflite::MicroMutableOpResolver<24> resolver;
  resolver.AddAdd();
  resolver.AddAveragePool2D();
  resolver.AddConcatenation();
  resolver.AddConv2D();
  resolver.AddDepthwiseConv2D();
  resolver.AddDequantize();
  resolver.AddFullyConnected();
  resolver.AddMaxPool2D();
  resolver.AddMean();
  resolver.AddMul();
  resolver.AddPad();
  resolver.AddPadV2();
  resolver.AddQuantize();
  resolver.AddRelu();
  resolver.AddRelu6();
  resolver.AddReshape();
  resolver.AddSoftmax();
  resolver.AddSqueeze();
  resolver.AddSub();

  MicroPrintf("resnet50: resolver ok\n");
  tflite::MicroInterpreter interpreter(model, resolver, tensor_arena,
                                       kTensorArenaSize);
  MicroPrintf("resnet50: AllocateTensors\n");
  TfLiteStatus alloc = interpreter.AllocateTensors();
  MicroPrintf("resnet50: allocate=%s arena_used=%d\n",
              alloc == kTfLiteOk ? "ok" : "FAIL",
              static_cast<int>(interpreter.arena_used_bytes()));
  if (alloc != kTfLiteOk) {
    return 1;
  }

  TfLiteTensor* input = interpreter.input(0);
  TfLiteTensor* output = interpreter.output(0);
  PrintTensor("input", input);
  PrintTensor("output", output);

  if (input == nullptr || input->data.raw == nullptr ||
      static_cast<int>(input->bytes) != g_input_image_data_size) {
    MicroPrintf("resnet50: input size mismatch model=%d blob=%d\n",
                input ? static_cast<int>(input->bytes) : -1,
                g_input_image_data_size);
    return 1;
  }
  memcpy(input->data.data, g_input_image_data, input->bytes);

  const uint32_t t0 = tflite::GetCurrentTimeTicks();
  TfLiteStatus inv = interpreter.Invoke();
  const uint32_t t1 = tflite::GetCurrentTimeTicks();
  const uint32_t tps = tflite::ticks_per_second();
  MicroPrintf("invoke: %s\n", inv == kTfLiteOk ? "ok" : "FAIL");
  if (tps == 0) {
    MicroPrintf("timing: ticks=%d ticks_per_sec=0 (no timer)\n",
                static_cast<int>(t1 - t0));
  } else {
    MicroPrintf("timing: ticks=%d ticks_per_sec=%d\n", static_cast<int>(t1 - t0),
                static_cast<int>(tps));
  }
  if (inv != kTfLiteOk) {
    return 1;
  }

  const int n = NumClasses(output);
  MicroPrintf("resnet50: num_classes=%d\n", n);
  int top_i[5] = {-1, -1, -1, -1, -1};
  float top_s[5] = {-1e30f, -1e30f, -1e30f, -1e30f, -1e30f};
  for (int i = 0; i < n; ++i) {
    const float s = Dequant(output, i);
    for (int r = 0; r < 5; ++r) {
      if (s > top_s[r]) {
        for (int k = 4; k > r; --k) {
          top_s[k] = top_s[k - 1];
          top_i[k] = top_i[k - 1];
        }
        top_s[r] = s;
        top_i[r] = i;
        break;
      }
    }
  }
  for (int r = 0; r < 5; ++r) {
    if (top_i[r] < 0) {
      break;
    }
    MicroPrintf("rank%d: %d %s %f", r + 1, top_i[r], Label(top_i[r]),
                static_cast<double>(top_s[r]));
  }
  if (top_i[0] >= 0) {
    MicroPrintf("top1: %d %s", top_i[0], Label(top_i[0]));
  }
  return 0;
}
