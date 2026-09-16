/*
 * QEMU AJIT1 System Emulator
 *
 * SPDX-License-Identifier: MIT
 *
 * Copyright (c) 2025 Redkill Technologies Pvt Ltd
 *
 * Permission is hereby granted, free of charge, to any person obtaining a copy
 * of this software and associated documentation files (the "Software"), to deal
 * in the Software without restriction, including without limitation the rights
 * to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
 * copies of the Software, and to permit persons to whom the Software is
 * furnished to do so, subject to the following conditions:
 *
 * The above copyright notice and this permission notice shall be included in
 * all copies or substantial portions of the Software.
 *
 * THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
 * IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
 * FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL
 * THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
 * LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
 * OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
 * THE SOFTWARE.
 */

#include "qemu/osdep.h"
#include "qemu/units.h"
#include "qemu/error-report.h"
#include "qapi/error.h"
#include "qemu/datadir.h"
#include "cpu.h"
#include "hw/irq.h"
#include "hw/qdev-properties.h"
#include "system/system.h"
#include "system/qtest.h"
#include "system/reset.h"
#include "hw/boards.h"
#include "hw/loader.h"
#include "elf.h"
#include "trace.h"

#include "hw/intc/ajit1_intc.h"
#include "hw/char/ajit1_uart.h"
#include "hw/timer/ajit1_timer.h"

#define AJIT1_PROM_FILENAME "ajit1-boot.bin"
#define AJIT1_PROM_OFFSET   (0x00000000)
#define AJIT1_PROM_SIZE     (0x00100000)
#define AJIT1_RAM_OFFSET    (AJIT1_PROM_OFFSET + AJIT1_PROM_SIZE)

#define AJIT1_TIMER_BASE_ADDR  (0xFFFF3100)
#define AJIT1_UART_BASE_ADDR   (0xFFFF3200)

#define AJIT1_SCRATCHPAD_BASE_ADDR  (0xFFFF2C00)
#define AJIT1_SCRATCHPAD_SIZE       (0x400)

#define AJIT1_UART_IRQ      (12)
#define AJIT1_TIMER_IRQ     (10)

/* Default system clock.  */
#define AJIT1_CPU_CLK (100 * 1000 * 1000)

/*
 * Scratch-pad MMIO ops. The scratch-pad SRAM is a non-cacheable AFB
 * peripheral memory window (manual: "afb_scratch_pad: AFB compatible
 * 32x32 scratchpad"), backed by a host byte buffer. Modelling it as
 * MMIO (not init_ram) keeps it out of QEMU's RAM fast path so it is
 * intrinsically non-cacheable, matching the silicon classification.
 *
 * AFB exposes only 32-bit word-aligned register-style accesses; byte,
 * halfword, doubleword and unaligned accesses are undefined on silicon
 * and are rejected by the MMIO valid filter below.
 */
static uint64_t ajit1_scratchpad_read(void *opaque, hwaddr addr,
                                      unsigned size)
{
    return ldl_be_p((const uint8_t *)opaque + addr);
}

static void ajit1_scratchpad_write(void *opaque, hwaddr addr,
                                   uint64_t val, unsigned size)
{
    stl_be_p((uint8_t *)opaque + addr, val);
}

/* Silicon clears the scratch-pad on reset. */
static void ajit1_scratchpad_reset(void *opaque)
{
    memset(opaque, 0, AJIT1_SCRATCHPAD_SIZE);
}

static const MemoryRegionOps ajit1_scratchpad_ops = {
    .read = ajit1_scratchpad_read,
    .write = ajit1_scratchpad_write,
    .endianness = DEVICE_BIG_ENDIAN,
    .impl = {
        .min_access_size = 4,
        .max_access_size = 4,
    },
    .valid = {
        .min_access_size = 4,
        .max_access_size = 4,
        .unaligned = false,
    },
};

typedef struct ResetData {
    struct CPUResetData {
        int id;
        SPARCCPU *cpu;
    } info[AJIT1_MAX_CPUS];

    /* save kernel entry in case of reset */
    uint32_t entry;
} ResetData;

static uint32_t *gen_store_u32(uint32_t *code, hwaddr addr, uint32_t val)
{
    /* mov %g0, %g1 */
    stl_p(code++, 0x82100000);

    /* mov %g0, %g2 */
    stl_p(code++, 0x84100000);

    /* sethi %hi(addr), %g1 */
    stl_p(code++, 0x03000000 + extract32(addr, 10, 22));

    /* or %g1, addr, %g1 */
    stl_p(code++, 0x82106000 + extract32(addr, 0, 10));

    /* sethi %hi(val), %g2 */
    stl_p(code++, 0x05000000 + extract32(val, 10, 22));

    /* or %g2, val, %g2 */
    stl_p(code++, 0x8410a000 + extract32(val, 0, 10));

    /* st %g2, [ %g1 ] */                              
    stl_p(code++, 0xc4204000);

    return code;
}

/*
 * When loading a kernel in RAM the machine is expected to be in a different
 * state (eg: initialized by the bootloader).  This little code reproduces
 * this behavior, & makes the cpu jump to entry of the kernel image.
 */
static void write_bootloader(void *ptr, hwaddr kernel_addr)
{
    uint32_t *p = ptr;

    uint32_t *sec_cpu_branch_p = NULL;

    /* If we are running on a secondary CPU, jump directly to the kernel.  */

    stl_p(p++, 0x85474000); /* rd %asr29, %g2      */
    stl_p(p++, 0x80908000); /* tst  %g2            */
    /* Filled below.  */
    sec_cpu_branch_p = p;
    stl_p(p++, 0x0BADC0DE); /* bne xxx             */
    stl_p(p++, 0x01000000); /* nop */

    /* 
     * Initialize the UART
     * *UART_CONTROL = UART_RX_ENABLE | UART_TX_ENABLE;
     */
    p = gen_store_u32(p, AJIT1_UART_BASE_ADDR, 3);

    /* Now, the relative branch above can be computed.  */
    stl_p(sec_cpu_branch_p, 0x12800000
          + (p - sec_cpu_branch_p));

    /* Jump to the entry point of the elf */

    /*mov %g0, %g1 */
    stl_p(p++, 0x82100000);

    /* sethi %hi(kernel_addr), %g1 */
    stl_p(p++, 0x03000000 + extract32(kernel_addr, 10, 22));

    /* or kernel_addr, %g1 */
    stl_p(p++, 0x82106000 + extract32(kernel_addr, 0, 10));

    /* jmp  %g1 */
    stl_p(p++, 0x81c04000);

    /* nop */
    stl_p(p++, 0x01000000);
}

static void ajit1_cpu_reset(void *opaque)
{
    struct CPUResetData *info = (struct CPUResetData *) opaque;
    int id = info->id;
    ResetData *s = container_of(info, ResetData, info[id]);
    CPUState *cpu = CPU(s->info[id].cpu);
    CPUSPARCState *env = cpu_env(cpu);

    cpu_reset(cpu);

    cpu->halted = false; // Start all CPUs
    env->pc = s->entry;
    env->npc = s->entry + 4;
}

static void ajit1_irq_manager(CPUSPARCState *env, int intno)
{
    CPUState *cpu = CPU(env_cpu(env));
    ajit1_intc_ack(env->irq_manager, cpu->cpu_index, intno & 0xF);
}

#define AJIT1_MAX_PILS 15

static uint32_t ajit1_find_active_pil(uint32_t pil_in)
{
    for (uint32_t i = AJIT1_MAX_PILS; i > 0; i--) {
        if (pil_in & (1 << i))
            return i;
    }
    return 0;
}

static uint32_t ajit1_should_handle_interrupt(CPUSPARCState *env)
{
    /*
     * interrupt_index = 0 means cpu is not handling any interrupt.
     * interrupt_index & ~AJIT1_MAX_PILS == TT_EXTINT means cpu is handling an
     * external interrupt.
     */
    return (env->interrupt_index == 0 || (env->interrupt_index & ~AJIT1_MAX_PILS) == TT_EXTINT);
}

static uint32_t ajit1_cpu_in_ext_irq(CPUSPARCState *env)
{
    return (env->interrupt_index & ~AJIT1_MAX_PILS) == TT_EXTINT;
}

/*
 * This is the handler called when the associated GPIO pil pin of a cpu is set.
 * This assumes that the incoming 'level' value on the qemu_irq is the mask
 * with bit corresponding to interrupt number set, not just a simple 0/1 level.
 */
static void ajit1_pil_in_handler(void *opaque, int n, int level)
{
    DeviceState *cpu = opaque;
    CPUState *cs = CPU(cpu);
    CPUSPARCState *env = cpu_env(cs);
    uint32_t cpu_should_handle_interrupt = 0;
    uint32_t valid_interrupt = 0;

    assert(env != NULL);

    env->pil_in = level;

    valid_interrupt = !!env->pil_in;

    cpu_should_handle_interrupt = ajit1_should_handle_interrupt(env);

    if (valid_interrupt && cpu_should_handle_interrupt) {
        uint32_t active_pil = ajit1_find_active_pil(env->pil_in);
        int old_interrupt = env->interrupt_index;

        /*Lower 4-bits of interrupt_index contain the interrupt number*/
        env->interrupt_index = TT_EXTINT | active_pil;

        /*
         * Trigger the interrupt if the old interrupt is not the same as the
         * incoming interrupt.
         */
        if (old_interrupt != env->interrupt_index){
            trace_ajit1_set_irq(active_pil);
            cpu_interrupt(cs, CPU_INTERRUPT_HARD);
        }

        return;
    }

    /*
     * When all interrupts are clear and the current interrupt is an external
     * interrupt then we pull down the hardware interrupt.
     */
    if (!valid_interrupt && ajit1_cpu_in_ext_irq(env)) {
        trace_ajit1_reset_irq(env->interrupt_index & 15);
        env->interrupt_index = 0;
        cpu_reset_interrupt(cs, CPU_INTERRUPT_HARD);
    }
}

static void ajit1_generic_hw_init(MachineState *machine)
{
    ram_addr_t ram_size = machine->ram_size;
    const char *bios_name = machine->firmware ?: AJIT1_PROM_FILENAME;
    const char *kernel_filename = machine->kernel_filename;
    SPARCCPU *cpu;
    CPUSPARCState   *env;
    MemoryRegion *address_space_mem = get_system_memory();
    MemoryRegion *prom = g_new(MemoryRegion, 1);
    MemoryRegion *scratchpad = g_new(MemoryRegion, 1);
    int         ret;
    char       *filename;
    int         bios_size = -1;
    ResetData  *reset_info;
    DeviceState *dev, *intcdev;
    qemu_irq uart_irq, timer_irq;

    reset_info = g_malloc0(sizeof(ResetData));

    for (uint32_t i = 0; i < machine->smp.cpus; i++) {
        /* Init CPU */
        cpu = SPARC_CPU(object_new(machine->cpu_type));
        qdev_init_gpio_in_named(DEVICE(cpu), ajit1_pil_in_handler, "pil", 1);
        qdev_realize(DEVICE(cpu), NULL, &error_fatal);
        env = &cpu->env;
        cpu_sparc_set_id(env, i);

        /* Reset data */
        reset_info->info[i].id = i;
        reset_info->info[i].cpu = cpu;
        qemu_register_reset(ajit1_cpu_reset, &reset_info->info[i]);
    }

    /* Allocate RAM */
    if (ram_size > 4 * GiB) {
        error_report("Too much memory for this machine: %" PRId64 "MB,"
                     " maximum 4G", ram_size / MiB);
        exit(1);
    }

    memory_region_add_subregion(address_space_mem, AJIT1_RAM_OFFSET, machine->ram);

    /* Allocate BIOS */
    memory_region_init_rom(prom, NULL, "ajit1.bios", AJIT1_PROM_SIZE, &error_fatal);
    memory_region_add_subregion(address_space_mem, AJIT1_PROM_OFFSET, prom);

    /* Load boot prom */
    filename = qemu_find_file(QEMU_FILE_TYPE_BIOS, bios_name);

    if (filename)
        bios_size = get_image_size(filename);

    if (bios_size > AJIT1_PROM_SIZE) {
        error_report("could not load prom '%s': file too big", filename);
        exit(1);
    }

    if (bios_size > 0) {
        ret = load_image_targphys(filename, AJIT1_PROM_OFFSET, bios_size);

        if (ret < 0 || ret > AJIT1_PROM_SIZE) {
            error_report("could not load prom '%s'", filename);
            exit(1);
        }
    } else if (kernel_filename == NULL && !qtest_enabled()) {
        error_report("Can't read bios image '%s'", filename ?: AJIT1_PROM_FILENAME);
        exit(1);
    }
    g_free(filename);

    /* Can directly load an application. */
    if (kernel_filename != NULL) {
        long     kernel_size;
        uint64_t entry;

        kernel_size = load_elf(kernel_filename, NULL, NULL, NULL,
                               &entry, NULL, NULL, NULL,
                               ELFDATA2MSB, EM_SPARC, 0, 0);

        if (kernel_size < 0) {
            kernel_size = load_uimage(kernel_filename, NULL, &entry,
                                      NULL, NULL, NULL);
        }

        if (kernel_size < 0) {
            error_report("could not load kernel '%s'", kernel_filename);
            exit(1);
        }

        if (bios_size <= 0) {
            /*
             * If there is no bios/monitor just start the application but put
             * the machine in an initialized state through a little
             * bootloader.
             */
            write_bootloader(memory_region_get_ram_ptr(prom), entry);
            reset_info->entry = AJIT1_PROM_OFFSET;
            for (uint32_t i = 0; i < machine->smp.cpus; i++) {
                reset_info->info[i].cpu->env.pc = AJIT1_PROM_OFFSET;
                reset_info->info[i].cpu->env.npc = AJIT1_PROM_OFFSET + 4;
            }
        }
    }

    /*
     * Register MMIO devices after ram setup so as to not overshadow the mmio
     * regions with ram. Overshadowing leads to mmio regions not being
     * registered properly and not used in flatview memory region translation
     * and hence eventually leads to not calling of mmio region r/w callbacks.
     */

    /*
     * Scratch-pad: non-cacheable peripheral SRAM window (AJIT manual
     * KC705/VC709 map). Backed by a host byte buffer through MMIO ops
     * so the region stays off QEMU's RAM fast path. Silicon clears it
     * on reset, so register a reset handler that re-zeros the buffer.
     */
    void *scratchpad_buf = g_malloc0(AJIT1_SCRATCHPAD_SIZE);
    memory_region_init_io(scratchpad, NULL, &ajit1_scratchpad_ops,
                          scratchpad_buf, "ajit1.scratchpad",
                          AJIT1_SCRATCHPAD_SIZE);
    memory_region_add_subregion(address_space_mem,
                                AJIT1_SCRATCHPAD_BASE_ADDR, scratchpad);
    qemu_register_reset(ajit1_scratchpad_reset, scratchpad_buf);

    /* Allocate interrupt controller */
    intcdev = qdev_new(TYPE_AJIT1_INTC);
    object_property_set_int(OBJECT(intcdev), "ncpus", machine->smp.cpus,
                            &error_fatal);
    sysbus_realize_and_unref(SYS_BUS_DEVICE(intcdev), &error_fatal);

    for (uint32_t i = 0; i < machine->smp.cpus; i++) {
        cpu = reset_info->info[i].cpu;
        env = &cpu->env;
        qdev_connect_gpio_out_named(intcdev, "ajit1-irq", i,
                                    qdev_get_gpio_in_named(DEVICE(cpu),
                                                           "pil", 0));
        env->irq_manager = intcdev;
        env->qemu_irq_ack = ajit1_irq_manager;
    }

    sysbus_mmio_map(SYS_BUS_DEVICE(intcdev), 0, AJIT1_INTC_BASE_ADDR);

    /* Allocate uart */
    dev = qdev_new(TYPE_AJIT1_UART);
    uart_irq = qdev_get_gpio_in(intcdev, AJIT1_UART_IRQ);

    qdev_prop_set_chr(dev, "chrdev", serial_hd(0));
    sysbus_realize_and_unref(SYS_BUS_DEVICE(dev), &error_fatal);
    sysbus_connect_irq(SYS_BUS_DEVICE(dev), 0, uart_irq);
    sysbus_mmio_map(SYS_BUS_DEVICE(dev), 0, AJIT1_UART_BASE_ADDR);

    /* Allocate timer */
    dev = qdev_new(TYPE_AJIT1_TIMER);
    timer_irq = qdev_get_gpio_in(intcdev, AJIT1_TIMER_IRQ);
    qdev_prop_set_uint32(dev, "frequency", AJIT1_CPU_CLK);
    sysbus_realize_and_unref(SYS_BUS_DEVICE(dev), &error_fatal);
    sysbus_connect_irq(SYS_BUS_DEVICE(dev), 0, timer_irq);
    sysbus_mmio_map(SYS_BUS_DEVICE(dev), 0, AJIT1_TIMER_BASE_ADDR);
}

static void ajit1_generic_machine_init(MachineClass *mc)
{
    mc->desc = "AJIT-1 generic";
    mc->init = ajit1_generic_hw_init;
    mc->default_cpu_type = SPARC_CPU_TYPE_NAME("AJIT1");
    mc->default_ram_id = "ajit1.ram";
    mc->max_cpus = AJIT1_MAX_CPUS;
}

DEFINE_MACHINE("ajit1_generic", ajit1_generic_machine_init)
