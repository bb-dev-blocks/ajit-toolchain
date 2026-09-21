/*========================================================*/
/*                                                        */
/* Linker script for Ajit Sparc      	                  */
/*                                                        */
/*========================================================*/

ENTRY(_start)
__DYNAMIC = 0;
SECTIONS
{
  . = {{ hex(confObj.software.program.getTextRegionStartAddr()) }};
  .text ALIGN(8) : {
    KEEP(*(.text.ajitstart))  /* NOTE: in file `init_00.s` */
    *(.text)
    *(.text.*)
    KEEP(*(.text.pagetablesetup)) /* NOTE: not needed */
    KEEP(*(.text.traphandlers))  /* NOTE: in file `trap_handlers.s` */
    KEEP(*(.text.traptablebase))  /* NOTE: in file `trap_handlers.s` */
  }

  . = {{ hex(confObj.software.program.getDataRegionStartAddr()) }};
  .rodata ALIGN(8) : {
    * (.rodata) * (.rodata.*)
    . = ALIGN(4);
    PROVIDE_HIDDEN (__preinit_array_start = .);
    KEEP (*(.preinit_array))
    PROVIDE_HIDDEN (__preinit_array_end = .);
    PROVIDE_HIDDEN (__init_array_start = .);
    KEEP (*(SORT(.init_array.*)))
    KEEP (*(.init_array))
    PROVIDE_HIDDEN (__init_array_end = .);
    PROVIDE_HIDDEN (__fini_array_start = .);
    KEEP (*(SORT(.fini_array.*)))
    KEEP (*(.fini_array))
    PROVIDE_HIDDEN (__fini_array_end = .);
    PROVIDE_HIDDEN (__tflite_ctor_start = .);
    KEEP (*(SORT(.ctors.*)))
    KEEP (*(.ctors))
    PROVIDE_HIDDEN (__tflite_ctor_end = .);
  }
  .data   ALIGN(8) : { * (.data) * (.data.*)}

  . = {{ hex(confObj.software.program.getBssRegionStartAddr()) }};
  /* .bss.* comes from -fdata-sections. Keep it in this output section so
     the measured .bss size includes large objects such as the tensor arena. */
  .bss   ALIGN(8) : { * (.bss) * (.bss.*) }
}
