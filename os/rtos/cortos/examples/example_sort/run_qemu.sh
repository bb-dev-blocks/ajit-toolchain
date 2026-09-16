#!/usr/bin/env bash
# Run this example on qemu-ajit (requires build_qemu.sh first).

cortos run --target qemu --timeout 300 "$@"
