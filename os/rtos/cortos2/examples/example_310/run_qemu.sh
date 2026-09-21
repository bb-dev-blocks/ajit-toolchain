#!/usr/bin/env bash
# Headless qemu-ajit run. Exit 0 iff expected_uart.txt matches.

cortos2 run --target qemu "$@"
