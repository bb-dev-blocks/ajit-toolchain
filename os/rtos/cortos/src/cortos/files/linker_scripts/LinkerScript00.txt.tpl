/* linker script for a program (0,0) (= a process) */

/*========================================================*/
/*                                                        */
/* Sample Linker script for Sparc simulator 	          */
/*                                                        */
/*========================================================*/

ENTRY(_start)
__DYNAMIC = 0;
SECTIONS
{
  . = {{hex(confObj.ramStartAddr)}}; /* (0,0) starts at zero.*/
  .text ALIGN(4) : {
    KEEP(*(.text.ajitstart))  /* NOTE: in file `init.s` */
    KEEP(*(.text.ajitstart.cortosloop))  /* NOTE: in file `init.s` */
    *(.text)
    *(.text.*)
    /* KEEP(*(.text.pagetablesetup)) */ /* NOTE: not needed */
    KEEP(*(.text.traphandlers))  /* NOTE: in file `trap_handlers.s` */
    KEEP(*(.text.traptablebase))  /* NOTE: in file `trap_handlers.s` */
  }

  .rodata ALIGN(4) : { * (.rodata) * (.rodata.*) }
  .preinit_array ALIGN(4) : {
    PROVIDE_HIDDEN (__preinit_array_start = .);
    KEEP (*(.preinit_array))
    PROVIDE_HIDDEN (__preinit_array_end = .);
  }
  .init_array ALIGN(4) : {
    PROVIDE_HIDDEN (__init_array_start = .);
    KEEP (*(SORT(.init_array.*)))
    KEEP (*(.init_array))
    PROVIDE_HIDDEN (__init_array_end = .);
  }
  .fini_array ALIGN(4) : {
    PROVIDE_HIDDEN (__fini_array_start = .);
    KEEP (*(SORT(.fini_array.*)))
    KEEP (*(.fini_array))
    PROVIDE_HIDDEN (__fini_array_end = .);
  }
  .ctors ALIGN(4) : {
    PROVIDE_HIDDEN (__tflite_ctor_start = .);
    KEEP (*(SORT(.ctors.*)))
    KEEP (*(.ctors))
    PROVIDE_HIDDEN (__tflite_ctor_end = .);
  }
  .data   ALIGN(4) : { * (.data) * (.data.*) *(.bss)}
}
