// Sized delete for TFLM virtual dtors when not linking libstdc++.
// Walk .init_array and .ctors so TEST() static registrars run before main.

extern "C" void (*__preinit_array_start[])(void);
extern "C" void (*__preinit_array_end[])(void);
extern "C" void (*__init_array_start[])(void);
extern "C" void (*__init_array_end[])(void);
extern "C" void (*__tflite_ctor_start[])(void);
extern "C" void (*__tflite_ctor_end[])(void);
extern "C" int main(int argc, char** argv);

static void tflite_call_array(void (**start)(void), void (**end)(void)) {
  for (void (**p)(void) = start; p < end; ++p) {
    if (*p) {
      (*p)();
    }
  }
}

extern "C" void tflite_call_ctors(void) {
  tflite_call_array(__preinit_array_start, __preinit_array_end);
  tflite_call_array(__init_array_start, __init_array_end);
  tflite_call_array(__tflite_ctor_start, __tflite_ctor_end);
}

extern "C" void tflite_cortos_start(void) {
  tflite_call_ctors();
  (void)main(0, nullptr);
}

void operator delete(void*) noexcept {}
void operator delete(void*, unsigned int) noexcept {}
void operator delete(void*, unsigned long) noexcept {}
void operator delete[](void*) noexcept {}
