#ifndef RESNET50_MODEL_BLOB_H_
#define RESNET50_MODEL_BLOB_H_

#include <cstdint>

// Symbols from sparc-linux-objcopy -I binary of gen/model.tflite.
extern "C" {
extern const uint8_t _binary_model_tflite_start[];
extern const uint8_t _binary_model_tflite_end[];
}

#endif
