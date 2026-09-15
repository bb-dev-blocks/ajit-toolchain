#!/usr/bin/env bash
# Host-gcc C runtimes from nested ahir/ into ahir_release/ (AHIR_RELEASE).
set -euo pipefail
if [[ -z "${AJIT_HOME:-}" || -z "${AHIR_RELEASE:-}" ]]; then
  echo "Need AJIT_HOME and AHIR_RELEASE (source set_ajit_home and ajit_env)."
  exit 1
fi
V="$AJIT_HOME/ahir/v2"
test -d "$V/pipeHandler/src"

mkdir -p "$V/pipeHandler/lib" "$V/CtestBench/lib" "$V/BitVectors/lib" "$V/functionLibrary/lib"
(
  cd "$V/pipeHandler"
  gcc -shared -fPIC -O2 -DNDEBUG -Iinclude -I../pthreadUtils/include \
    src/pipeHandler.c src/Pipes.c -lpthread -o lib/libPipeHandler.so
  gcc -shared -fPIC -g -DNDEBUG -Iinclude -I../pthreadUtils/include \
    src/pipeHandler.c src/Pipes.c -lpthread -o lib/libPipeHandlerDebugPthreads.so
)
(
  cd "$V/CtestBench"
  gcc -shared -fPIC -g -DNDEBUG -Iinclude -I../pthreadUtils/include \
    src/SocketLib.c src/SockPipes.c -o lib/libSockPipes.so
)
(
  cd "$V/BitVectors"
  gcc -c -fPIC -g -Iinclude -I../CtestBench/include -I../pipeHandler/include src/*.c
  ar rcs lib/libBitVectors.a *.o
  rm -f *.o
)
(
  cd "$V/functionLibrary"
  gcc -shared -fPIC -g -Iinclude src/fpu.c -o lib/libfpu.so
  gcc -shared -fPIC -g -Iinclude src/timer.c -o lib/libtimer.so
  gcc -shared -fPIC -g -Iinclude src/llvm_intrinsics.c -o lib/libllvm_intrinsics.so
)

cp -f "$V/pipeHandler/lib/libPipeHandler.so" "$V/pipeHandler/lib/libPipeHandlerDebugPthreads.so" \
  "$V/CtestBench/lib/libSockPipes.so" "$V/BitVectors/lib/libBitVectors.a" \
  "$AHIR_RELEASE/lib/"
cp -f "$V/functionLibrary/lib/"lib{fpu,timer,llvm_intrinsics}.so "$AHIR_RELEASE/functionLibrary/lib/"
file "$AHIR_RELEASE/lib/libPipeHandlerDebugPthreads.so"
