// Runs one ResNet-50 op (selected at build time) through its TFLM kernel and
// prints the C-model cycle count of Invoke plus an output checksum.
//
// gen/layer_params.h and gen/liblayerblob.a come from generate_layer.py.
// Activations are deterministic pseudo-random int8 data; weights, bias and
// other constants are the model's own.

#include <cstdint>
#include <cstring>

#include "layer_params.h"
#include "layer_runner.h"
#include "tensorflow/lite/c/builtin_op_data.h"
#include "tensorflow/lite/c/common.h"
#include "tensorflow/lite/micro/kernels/micro_ops.h"
#include "tensorflow/lite/micro/micro_log.h"

extern "C" {
extern const uint8_t _binary_layer_data_bin_start[];
uint64_t cortos_get_clock_time();
}

namespace {

constexpr int kScaleCount = sizeof(layer::kScales) / sizeof(layer::kScales[0]);

alignas(16) uint8_t g_act[layer::kActBytes];
TfLiteTensor g_tensors[layer::kNumTensors];
TfLiteAffineQuantization g_quant[layer::kNumTensors];
// TfLiteIntArray / TfLiteFloatArray storage: {size, values...} per array.
int32_t g_dims_pool[layer::kNumTensors * 6];
int32_t g_q_pool[layer::kNumTensors * 4 + 2 * kScaleCount];
int g_inputs[1 + layer::kNumInputs];
int g_outputs[2];

TFLMRegistration Registration(int kind) {
  switch (kind) {
    case 0: return tflite::Register_CONV_2D();
    case 1: return tflite::Register_FULLY_CONNECTED();
    case 2: return tflite::Register_ADD();
    case 3: return tflite::Register_SUB();
    case 4: return tflite::Register_MUL();
    case 5: return tflite::Register_PAD();
    case 6: return tflite::Register_CONCATENATION();
    case 7: return tflite::Register_QUANTIZE();
    case 8: return tflite::Register_MAX_POOL_2D();
    default: return tflite::Register_MEAN();
  }
}

union BuiltinData {
  TfLiteConvParams conv;
  TfLiteFullyConnectedParams fc;
  TfLiteAddParams add;
  TfLiteSubParams sub;
  TfLiteMulParams mul;
  TfLiteConcatenationParams concat;
  TfLitePoolParams pool;
  TfLiteReducerParams reducer;
};
BuiltinData g_builtin;

const void* Builtin(int kind) {
  memset(&g_builtin, 0, sizeof(g_builtin));
  auto act = static_cast<TfLiteFusedActivation>(layer::k_activation);
  switch (kind) {
    case 0:
      g_builtin.conv.padding = static_cast<TfLitePadding>(layer::k_padding);
      g_builtin.conv.stride_width = layer::k_stride_w;
      g_builtin.conv.stride_height = layer::k_stride_h;
      g_builtin.conv.dilation_width_factor = layer::k_dil_w;
      g_builtin.conv.dilation_height_factor = layer::k_dil_h;
      g_builtin.conv.activation = act;
      g_builtin.conv.quantized_bias_type = kTfLiteNoType;
      return &g_builtin.conv;
    case 1:
      g_builtin.fc.activation = act;
      g_builtin.fc.keep_num_dims = layer::k_keep_num_dims != 0;
      g_builtin.fc.quantized_bias_type = kTfLiteNoType;
      return &g_builtin.fc;
    case 2: g_builtin.add.activation = act; return &g_builtin.add;
    case 3: g_builtin.sub.activation = act; return &g_builtin.sub;
    case 4: g_builtin.mul.activation = act; return &g_builtin.mul;
    case 6:
      g_builtin.concat.axis = layer::k_axis;
      g_builtin.concat.activation = act;
      return &g_builtin.concat;
    case 8:
      g_builtin.pool.padding = static_cast<TfLitePadding>(layer::k_padding);
      g_builtin.pool.stride_width = layer::k_stride_w;
      g_builtin.pool.stride_height = layer::k_stride_h;
      g_builtin.pool.filter_width = layer::k_filter_w;
      g_builtin.pool.filter_height = layer::k_filter_h;
      g_builtin.pool.activation = act;
      return &g_builtin.pool;
    case 9:
      g_builtin.reducer.keep_dims = layer::k_keep_dims != 0;
      return &g_builtin.reducer;
    default:
      return nullptr;  // PAD, QUANTIZE take no builtin options.
  }
}

// Deterministic activation-like input. int8: zero point + [0, 31], i.e. small
// non-negative real values as after ReLU (full-range noise saturates most conv
// outputs and makes the checksum blind to weights/bias). float32: [-2, 2).
void FillPseudoRandom(const layer::TensorDesc& d, uint8_t* p) {
  uint32_t s = 0x12345678u;
  const int zp = d.q_n > 0 ? layer::kZeroPoints[d.q_off] : 0;
  if (d.type == kTfLiteFloat32) {
    float* f = reinterpret_cast<float*>(p);
    for (uint32_t i = 0; i < d.bytes / 4; ++i) {
      s = s * 1664525u + 1013904223u;
      f[i] = (static_cast<int>(s >> 24) - 128) / 64.0f;
    }
    return;
  }
  for (uint32_t i = 0; i < d.bytes; ++i) {
    s = s * 1664525u + 1013904223u;
    int v = zp + static_cast<int>((s >> 24) & 31u);
    p[i] = static_cast<uint8_t>(static_cast<int8_t>(v > 127 ? 127 : v));
  }
}

uint32_t Fnv1a(const uint8_t* p, uint32_t n) {
  uint32_t h = 2166136261u;
  for (uint32_t i = 0; i < n; ++i) h = (h ^ p[i]) * 16777619u;
  return h;
}

void BuildTensors() {
  int32_t* q = g_q_pool;
  for (int i = 0; i < layer::kNumTensors; ++i) {
    const layer::TensorDesc& d = layer::kTensors[i];
    TfLiteTensor& t = g_tensors[i];
    memset(&t, 0, sizeof(t));
    if (d.src == 3) continue;
    int32_t* dims = &g_dims_pool[i * 6];
    for (int k = 0; k <= d.dims[0]; ++k) dims[k] = d.dims[k];
    t.dims = reinterpret_cast<TfLiteIntArray*>(dims);
    t.type = static_cast<TfLiteType>(d.type);
    t.bytes = d.bytes;
    if (d.src == 0) {
      t.data.raw = const_cast<char*>(reinterpret_cast<const char*>(
          _binary_layer_data_bin_start + d.offset));
      t.allocation_type = kTfLiteMmapRo;
    } else {
      t.data.raw = reinterpret_cast<char*>(g_act + d.offset);
      t.allocation_type = kTfLiteArenaRw;
      if (d.src == 1) FillPseudoRandom(d, g_act + d.offset);
    }
    if (d.q_n > 0) {
      TfLiteFloatArray* scales = reinterpret_cast<TfLiteFloatArray*>(q);
      scales->size = d.q_n;
      for (int k = 0; k < d.q_n; ++k)
        scales->data[k] = layer::kScales[d.q_off + k];
      q += 1 + d.q_n;
      TfLiteIntArray* zps = reinterpret_cast<TfLiteIntArray*>(q);
      zps->size = d.q_n;
      for (int k = 0; k < d.q_n; ++k)
        zps->data[k] = layer::kZeroPoints[d.q_off + k];
      q += 1 + d.q_n;
      g_quant[i].scale = scales;
      g_quant[i].zero_point = zps;
      g_quant[i].quantized_dimension = d.q_dim;
      t.quantization.type = kTfLiteAffineQuantization;
      t.quantization.params = &g_quant[i];
      t.params.scale = scales->data[0];
      t.params.zero_point = zps->data[0];
    }
  }
  g_inputs[0] = layer::kNumInputs;
  for (int i = 0; i < layer::kNumInputs; ++i)
    g_inputs[1 + i] = layer::kTensors[i].src == 3 ? kTfLiteOptionalTensor : i;
  g_outputs[0] = 1;
  g_outputs[1] = layer::kNumInputs;
}

}  // namespace

int main() {
  BuildTensors();
  LayerRunner runner(Registration(layer::kKindId), g_tensors,
                     layer::kNumTensors,
                     reinterpret_cast<TfLiteIntArray*>(g_inputs),
                     reinterpret_cast<TfLiteIntArray*>(g_outputs),
                     Builtin(layer::kKindId));
  MicroPrintf("layer: op=%d kind=%s rows=%d work=%u unit=%s", layer::kOpIndex,
              layer::kKind, layer::kRows, static_cast<unsigned>(layer::kWork),
              layer::kWorkUnit);
  if (runner.InitAndPrepare() != kTfLiteOk) {
    MicroPrintf("prepare: FAIL");
    return 1;
  }
  const uint64_t t0 = cortos_get_clock_time();
  const TfLiteStatus status = runner.Invoke();
  const uint64_t t1 = cortos_get_clock_time();
  MicroPrintf("invoke: %s", status == kTfLiteOk ? "ok" : "FAIL");
  MicroPrintf("cycles: %u", static_cast<unsigned>(t1 - t0));
  const layer::TensorDesc& out = layer::kTensors[layer::kNumInputs];
  MicroPrintf("checksum: %x", static_cast<unsigned>(
                                  Fnv1a(g_act + out.offset, out.bytes)));
  MicroPrintf("layer_done");
  return 0;
}
