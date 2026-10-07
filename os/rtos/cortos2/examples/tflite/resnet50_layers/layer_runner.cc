#include "layer_runner.h"

#include "tensorflow/lite/micro/micro_arena_constants.h"
#include "tensorflow/lite/micro/micro_context.h"
#include "tensorflow/lite/micro/micro_log.h"

alignas(tflite::MicroArenaBufferAlignment()) uint8_t
    LayerRunner::arena_[LayerRunner::kArenaSize];

namespace {
void ClearBufferApi(TfLiteContext* context) {
  context->GetScratchBuffer = nullptr;
  context->GetExternalContext = nullptr;
  context->AllocatePersistentBuffer = nullptr;
  context->RequestScratchBufferInArena = nullptr;
}
}  // namespace

LayerRunner::LayerRunner(const TFLMRegistration& registration,
                         TfLiteTensor* tensors, int tensors_size,
                         TfLiteIntArray* inputs, TfLiteIntArray* outputs,
                         const void* builtin_data)
    : registration_(registration),
      allocator_(tflite::SingleArenaBufferAllocator::Create(arena_,
                                                            kArenaSize)),
      mock_micro_graph_(allocator_),
      fake_micro_context_(tensors, allocator_, &mock_micro_graph_) {
  (void)tensors_size;
  context_.impl_ = static_cast<void*>(&fake_micro_context_);
  context_.ReportError = tflite::MicroContextReportOpError;
  context_.GetTensor = tflite::MicroContextGetTensor;
  context_.GetEvalTensor = tflite::MicroContextGetEvalTensor;
  ClearBufferApi(&context_);
  context_.AllocatePersistentBuffer = tflite::MicroContextAllocatePersistentBuffer;
  context_.recommended_num_threads = 0;
  node_.inputs = inputs;
  node_.outputs = outputs;
  node_.builtin_data = const_cast<void*>(builtin_data);
}

TfLiteStatus LayerRunner::InitAndPrepare() {
  if (registration_.init) {
    ClearBufferApi(&context_);
    context_.AllocatePersistentBuffer =
        tflite::MicroContextAllocatePersistentBuffer;
    node_.user_data = registration_.init(&context_, nullptr, 0);
  }
  if (registration_.prepare) {
    ClearBufferApi(&context_);
    context_.AllocatePersistentBuffer =
        tflite::MicroContextAllocatePersistentBuffer;
    context_.RequestScratchBufferInArena =
        tflite::MicroContextRequestScratchBufferInArena;
    context_.GetExternalContext = tflite::MicroContextGetExternalContext;
    TF_LITE_ENSURE_STATUS(registration_.prepare(&context_, &node_));
  }
  return kTfLiteOk;
}

TfLiteStatus LayerRunner::Invoke() {
  ClearBufferApi(&context_);
  context_.GetScratchBuffer = tflite::MicroContextGetScratchBuffer;
  return registration_.invoke(&context_, &node_);
}
