// Single-op driver: TFLM KernelRunner logic with a larger kernel arena.
//
// KernelRunner's arena is a fixed 10000 bytes; Prepare of a conv with
// 1024-2048 output channels needs more (per-channel multipliers and shifts).
// This class calls the same registration hooks against the library's
// FakeMicroContext and MockMicroGraph, so the measured kernel code is exactly
// what libtensorflow-microlite.a provides.

#ifndef RESNET50_LAYERS_LAYER_RUNNER_H_
#define RESNET50_LAYERS_LAYER_RUNNER_H_

#include "tensorflow/lite/c/common.h"
#include "tensorflow/lite/micro/arena_allocator/single_arena_buffer_allocator.h"
#include "tensorflow/lite/micro/fake_micro_context.h"
#include "tensorflow/lite/micro/micro_common.h"
#include "tensorflow/lite/micro/mock_micro_graph.h"

class LayerRunner {
 public:
  LayerRunner(const TFLMRegistration& registration, TfLiteTensor* tensors,
              int tensors_size, TfLiteIntArray* inputs,
              TfLiteIntArray* outputs, const void* builtin_data);

  TfLiteStatus InitAndPrepare();
  TfLiteStatus Invoke();

 private:
  static constexpr int kArenaSize = 256 * 1024;
  static uint8_t arena_[kArenaSize];

  TfLiteContext context_ = {};
  TfLiteNode node_ = {};
  const TFLMRegistration& registration_;
  tflite::SingleArenaBufferAllocator* allocator_;
  tflite::MockMicroGraph mock_micro_graph_;
  tflite::FakeMicroContext fake_micro_context_;
};

#endif  // RESNET50_LAYERS_LAYER_RUNNER_H_
