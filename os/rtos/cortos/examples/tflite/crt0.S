! Bare-metal AJIT start for qemu-ajit (RAM 0x00100000). Window traps live in
! the shared CoRTOS trap table. DebugLog talks UART; this file only boots.

.section .text.ajitstart
.global _start
_start:
  set 0x10E0, %l0
  wr %l0, %psr
  set 0x2, %l0
  wr %l0, %g0, %wim
  nop
  nop
  nop
  set trap_table_base, %l0
  wr %l0, %g0, %tbr
  set _stack_top, %sp
  andn %sp, 7, %sp
  add %sp, -96, %sp
  call tflite_clear_bss
  nop
  call tflite_call_ctors
  nop
  call main
  nop
  ta 0

.global tflite_clear_bss
tflite_clear_bss:
  set _bss_start, %o0
  set _bss_end, %o1
1:
  cmp %o0, %o1
  bge 2f
  nop
  st %g0, [%o0]
  add %o0, 4, %o0
  ba 1b
  nop
2:
  retl
  nop
