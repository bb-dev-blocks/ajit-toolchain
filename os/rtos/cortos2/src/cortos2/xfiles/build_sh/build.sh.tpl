
# This is a bash script to build the cortos project.
# It generates a mmap file which is used in the `run_cmodel.sh`,
# to run the program on the C simulator.

_MAIN="main";
_CORTOS_SRC_DIR="cortos_src";

_CORTOS_VMAP="$_CORTOS_SRC_DIR/vmap.txt";
_LINKER_SCRIPT="$_CORTOS_SRC_DIR/LinkerScript.txt";

_PT="$AJIT_MINIMAL_PRINTF_TIMER";
_AAR_MT="$AJIT_ACCESS_ROUTINES_MT";
_AAR="$AJIT_ACCESS_ROUTINES";
_IEEE_SOFT_FLOAT_LIB="$AJIT_HOME/application_development/soft_float/ieeelib/"
# {{ confObj.software.build.debug }}
% if confObj.software.extraCc:
_TFLITE_CXXFLAGS="-S -fno-pic -fno-pie -m32 -mcpu=v8 -std=c++17 -fno-rtti -fno-exceptions -fno-threadsafe-statics -fno-use-cxa-atexit -fpermissive -fno-builtin-printf -funsigned-char -fno-delete-null-pointer-checks -fomit-frame-pointer -ffunction-sections -fdata-sections -DTF_LITE_STATIC_MEMORY -DTF_LITE_DISABLE_X86_NEON -DTF_LITE_MCU_DEBUG_LOG -DTF_LITE_USE_GLOBAL_CMATH_FUNCTIONS -DTF_LITE_USE_GLOBAL_MIN -DTF_LITE_USE_GLOBAL_MAX -I${AJIT_UCLIBC_HEADERS_DIR}"
% for inc in confObj.software.extraIncludes:
_TFLITE_CXXFLAGS="${_TFLITE_CXXFLAGS} -I {{inc}}"
% end
% for i, cc in enumerate(confObj.software.extraCc):
sparc-linux-g++ ${_TFLITE_CXXFLAGS} "{{cc}}" -o extra_cc_{{i}}.s
% end
% end
compileToSparcUclibc.py \
% if confObj.software.build.debug:
  -g \
% end
  -o {{ confObj.software.build.optLevel }} \
% if confObj.hardware.cpu.mmu and confObj.target.enable_mmu:
  -V ${_CORTOS_VMAP} \
  -R .. \
% end
  -I ${AJIT_UCLIBC_HEADERS_DIR} \
  -I ${AJIT_LIBGCC_INSTALL_DIR}/include \
  -I . \
  -I .. \
  -I ${_CORTOS_SRC_DIR} \
  -I ${_AAR_MT}/include \
  -I ${_PT}/include \
  -S .. \
  -S ${_CORTOS_SRC_DIR} \
  -C .. \
  -C ${_CORTOS_SRC_DIR} \
% for i, cc in enumerate(confObj.software.extraCc):
  -s extra_cc_{{i}}.s \
% end
  -l .. \
% for d in confObj.software.extraLibDirs:
  -l {{d}} \
% end
  -N ${_MAIN} \
  -L ${_LINKER_SCRIPT} \
% if confObj.software.build.useLibAjit:
  -l ${_AAR_MT}/lib\
  % if  confObj.software.build.useDefaultLibAjit:
    -a ajit_default\
  % else:
    -a ajit_alt\
  % end
% else :
  -s ${_AAR_MT}/asm/clear_stack_pointers.s \
  -s ${_AAR_MT}/asm/generic_isr_mt.s \
  -s ${_AAR_MT}/asm/generic_sw_trap_mt.s \
  -s ${_AAR_MT}/asm/generic_sys_calls.s \
  -s ${_AAR_MT}/asm/mutexes.s \
  -C ${_AAR_MT}/src \
% end
  -D AJIT \
  -U \
  {{ confObj.software.build.buildArgs }};

% if not confObj.target.enable_mmu:
# qemu -kernel jumps to ELF e_entry; compileToSparcUclibc.py passes -e main.
_START=$(sparc-linux-nm ${_MAIN}.elf | awk '/ _start$/{print $1}')
sparc-linux-objcopy --set-start "0x${_START}" ${_MAIN}.elf
% end

#  -s ${_AAR_MT}/asm/clear_stack_pointers.s \
#  -s ${_AAR_MT}/asm/trap_handlers_for_rtos.s \
#  -s ${_AAR_MT}/asm/generic_isr_mt.s \
#  -s ${_AAR_MT}/asm/generic_sw_trap_mt.s \
#  -C ${_AAR}/src \
#  -S ${_AAR_MT}/asm \
