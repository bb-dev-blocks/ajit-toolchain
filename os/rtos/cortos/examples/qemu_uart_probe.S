/* Minimal qemu-ajit UART probe. Link at 0x00100000. Not a CoRTOS example. */
        .text
        .global _start
_start:
        set     0xFFFF3200, %g1
        mov     3, %g2
        st      %g2, [%g1]
        set     0xFFFF3204, %g1
        sethi   %hi(msg), %g3
        or      %g3, %lo(msg), %g3
1:
        ldub    [%g3], %g2
        cmp     %g2, 0
        be      2f
        nop
3:
        ld      [%g1 - 4], %g4
        andcc   %g4, 8, %g0
        bne     3b
        nop
        stb     %g2, [%g1]
        add     %g3, 1, %g3
        ba      1b
        nop
2:
        ba      2b
        nop
        .section .rodata
msg:
        .asciz  "Hello There\n"
