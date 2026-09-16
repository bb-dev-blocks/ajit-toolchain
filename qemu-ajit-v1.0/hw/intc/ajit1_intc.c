/*
 * QEMU AJIT1 Interrupt Controller Emulator
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
#include "hw/irq.h"
#include "hw/sysbus.h"
#include "hw/qdev-properties.h"
#include "qapi/error.h"
#include "qemu/module.h"
#include "qom/object.h"

#include "hw/intc/ajit1_intc.h"
#include "trace.h"

/* 
 * Each Controller specific to a core & thread is called a TIC(Thread interrupt
 * controller).
 */

/* Each TIC follows a state machine with the following states */
typedef enum {
    AJIT1_TIC_DISABLED,
    AJIT1_TIC_ENABLED,
    AJIT1_TIC_INTERRUPTING
} ajit1_tic_state_t;

/*
 * Each TIC has a 32-bit control register with the below layout:
 * BIT[31:17] : interrupt vector (which interrupts are currently active?)
 * BIT[16]    : unused
 * BIT[15:1]  : interrupt mask (if bit is set, the interrupt is recognized)
 * BIT[0]     : enabled
*/
struct ajit1_tic_t {
    uint32_t             control;
    ajit1_tic_state_t    state;
    uint32_t             pil_pending;
};

struct ajit1_intc_ipi {
	uint32_t         intr_mask;
	uint32_t         intr_val;
	uint32_t         msg_hi[AJIT1_INTC_MAX_CPU];
	uint32_t         msg_lo[AJIT1_INTC_MAX_CPU];
	uint32_t         lock;
};

typedef struct ajit1_intc_ipi ajit1_intc_ipi_t;

typedef struct ajit1_tic_t ajit1_tic_t;

OBJECT_DECLARE_SIMPLE_TYPE(ajit1_intc_state, AJIT1_INTC)

struct ajit1_intc_state {
    SysBusDevice         parent_obj;

    /*memory mapped register space*/
    MemoryRegion         iomem;

    /*number of cpus configured on the qemu cmdline*/
    unsigned int         ncpus;

    /*per-cpu thread-interrupt-controller instances*/
    ajit1_tic_t          tic[AJIT1_INTC_MAX_CPU];

    /*per-cpu irq object instance representing an individual pil line to cpu*/
    qemu_irq             irq[AJIT1_INTC_MAX_CPU];

    ajit1_intc_ipi_t      ipi;
};

static uint32_t ajit1_is_tic_enabled(ajit1_tic_t *tic)
{
    return (tic->control & 0x1);
}

static void ajit1_clear_active_irq(ajit1_tic_t *t)
{
    uint32_t control = t->control;
    control &= ((0x1 << 17) - 1);
    t->control = control;
}

static void ajit1_intc_ack_cpu(ajit1_intc_state *intc, unsigned int cpu, int intno)
{
    ajit1_tic_t *tic = &intc->tic[cpu];

    if (ajit1_is_tic_enabled(tic)){
        uint32_t pending;
        trace_ajit1_intc_ack_irq(intno, cpu);
        ajit1_clear_active_irq(tic);
        qatomic_and(&tic->pil_pending, ~(1u << intno));
        pending = qatomic_read(&tic->pil_pending);
        if (pending)
            qemu_set_irq(intc->irq[cpu], pending);
        else
            qemu_irq_lower(intc->irq[cpu]);
    }
}

void ajit1_intc_ack(DeviceState *dev, unsigned int cpu, int intno)
{
    ajit1_intc_state *intc = AJIT1_INTC(dev);
    ajit1_intc_ack_cpu(intc, cpu, intno);
}

/*Determines if the specified IRQ is enabled at the TIC level*/
static bool ajit1_irq_is_enabled(ajit1_tic_t *t, int irq)
{
    uint32_t control = t->control;

    if (control & (1 << irq))
        return true;

    return false;
}

static void ajit1_intc_set_irq_cpu(ajit1_intc_state *intc, int irq, int level, int cpu)
{
    ajit1_tic_t *tic = &intc->tic[cpu];

    if (level) {
        uint32_t pending;
        qatomic_or(&tic->pil_pending, 1u << irq);
        if (ajit1_irq_is_enabled(tic, irq)) {
            trace_ajit1_intc_set_irq(irq, level, cpu);
            tic->control |= (irq << 17);
            pending = qatomic_read(&tic->pil_pending);
            qemu_set_irq(intc->irq[cpu], pending);
        }
    }
}

static void ajit1_intc_set_irq(void *opaque, int irq, int level)
{
    ajit1_intc_state *intc = AJIT1_INTC(opaque);

    /*Raise the irq to all available non-masked cpu*/
    for (uint32_t cpu = 0; cpu < intc->ncpus; cpu++){
	    ajit1_intc_set_irq_cpu(intc, irq, level, cpu);
    }
}

static uint32_t ajit1_find_cpu_index(void)
{
    uint32_t cpu_idx = 0;
    CPUState *__cpu = current_cpu;

    if (__cpu)
	    cpu_idx = __cpu->cpu_index;
    return cpu_idx;
}

static MemTxResult ajit1_intc_read(void *opaque, hwaddr addr, uint64_t *data,
                                 unsigned size, MemTxAttrs attrs)
{
    ajit1_intc_state *intc = opaque;
    uint32_t cpu_idx = ajit1_find_cpu_index();
    ajit1_tic_t *tic = &intc->tic[cpu_idx];
    uint32_t val = 0;

    assert(intc != NULL);

    switch (addr) {
    case AJIT1_INTC_IPI_INTR_MASK:
        val = intc->ipi.intr_mask;
        break;
    case AJIT1_INTC_IPI_INT_VAL:
        val = intc->ipi.intr_val;
        break;
    case AJIT1_INTC_IPI_LOCK:
        val = intc->ipi.lock;
        break;
    case AJIT1_INTC_CTRL_OFFSET ... 0x20:
        val = tic->control;
        break;
    default:
        for (uint32_t cpu = 0; cpu < intc->ncpus; cpu++) {
            if (addr == AJIT1_INTC_IPI_MSG_HI(cpu)) {
                    val = intc->ipi.msg_hi[cpu];
                    break;
            }
            if (addr == AJIT1_INTC_IPI_MSG_LO(cpu)) {
                    val = intc->ipi.msg_lo[cpu];
                    break;
            }
        }

        break;
    }

    trace_ajit1_intc_read(addr, val, cpu_idx);
    *data = val;
    return MEMTX_OK;
}

#include "qemu/osdep.h"
#include "hw/core/cpu.h"

static MemTxResult ajit1_intc_write(void *opaque, hwaddr addr,
                              uint64_t value, unsigned size, MemTxAttrs attrs)
{
    ajit1_intc_state *intc = opaque;
    uint32_t cpu_idx = ajit1_find_cpu_index();
    ajit1_tic_t *tic;
    uint32_t old, cpu_bit;
    int idx;

    assert(intc != NULL);
    tic = &intc->tic[cpu_idx];
    trace_ajit1_intc_write(addr, value, cpu_idx);

    /* global registers */
    switch (addr) {
    case AJIT1_INTC_CTRL_OFFSET ... 0x20:
        value &= 0xFFFFFFFF; /* clean up the value */
        tic->control = value;
        if (value & 0x1) {
                uint32_t pending;
                tic->state = AJIT1_TIC_ENABLED;
                pending = qatomic_read(&tic->pil_pending);
                if (pending & value)
                    qemu_set_irq(intc->irq[cpu_idx], pending);
        }
        break;
    case AJIT1_INTC_IPI_INTR_MASK:
        old = intc->ipi.intr_mask;
        /*
         * value == (old | (1 << cpu_idx)).
         * So, ctz32 gives the cpu index.
         */
        cpu_bit = old ^ value;
        idx = ctz32(cpu_bit);
        intc->ipi.intr_mask = value;
        if (cpu_bit) {
                /*
                 * Trigger an IPI when a new CPU bit is set in IPI_INTR_MASK
                 * while the IPI_INT_VAL is set for that CPU.
                 */
                if ((value & cpu_bit) && (intc->ipi.intr_val & cpu_bit)) {
                    ajit1_intc_set_irq_cpu(intc, AJIT1_INTC_IPI_NR, 1, idx);
                }
        }
        break;
    case AJIT1_INTC_IPI_INT_VAL:
        old = intc->ipi.intr_val;
        cpu_bit = old ^ value;
        idx = ctz32(cpu_bit);
        intc->ipi.intr_val = value;
        if (cpu_bit) {
                /*
                 * Send an ACK when CPU bit is cleared in IPI_INT_VAL.
                 */
                if (old & cpu_bit) {
                    ajit1_intc_ack_cpu(intc, idx, AJIT1_INTC_IPI_NR);
                }
        }
        break;
    case AJIT1_INTC_IPI_LOCK:
        intc->ipi.lock = value;
        break;
    default:
        for (uint32_t cpu = 0; cpu < intc->ncpus; cpu++) {
            if (addr == AJIT1_INTC_IPI_MSG_HI(cpu)) {
                intc->ipi.msg_hi[cpu] = value;
                break;
            }
            if (addr == AJIT1_INTC_IPI_MSG_LO(cpu)) {
                intc->ipi.msg_lo[cpu] = value;
                break;
            }
        }

        break;
    }

    return MEMTX_OK;
}

/*
 * Use *_with_attrs callbacks to allow atomic accesses
 * on AJIT1_INTC_IPI_LOCK.
 */
static const MemoryRegionOps ajit1_intc_ops = {
    .write_with_attrs = ajit1_intc_write,
    .read_with_attrs = ajit1_intc_read,
    .endianness = DEVICE_NATIVE_ENDIAN,
    .valid = {
        .min_access_size = 1, // Byte accesses for AJIT1_INTC_IPI_LOCK
        .max_access_size = 4,
    },
};

/*
 * On reset:
 * state := AJIT1_INTC_DISABLED
 * control_reg := 0
 * For each TIC
 */
static void ajit1_intc_reset(DeviceState *dev)
{
    ajit1_intc_state *intc = AJIT1_INTC(dev);
    ajit1_tic_t *tic;

    for (uint32_t cpu = 0; cpu < intc->ncpus; cpu++){
        tic = &intc->tic[cpu];
        tic->control = 0;
        tic->state = AJIT1_TIC_DISABLED;
        tic->pil_pending = 0;
    }
}

static void ajit1_intc_realize(DeviceState *dev, Error **errp)
{
    ajit1_intc_state *intc = AJIT1_INTC(dev);
    SysBusDevice *sbd = SYS_BUS_DEVICE(dev);

    if ((!intc->ncpus) || (intc->ncpus > AJIT1_INTC_MAX_CPU)) {
        error_setg(errp, "Invalid ncpus properties: "
                   "%u, must be 0 < ncpus =< %u.", intc->ncpus,
                   AJIT1_INTC_MAX_CPU);
        return;
    }

    qdev_init_gpio_in(dev, ajit1_intc_set_irq, AJIT1_INTC_MAX_PILS);
    qdev_init_gpio_out_named(dev, intc->irq, "ajit1-irq", intc->ncpus);

    memory_region_init_io(&intc->iomem, OBJECT(intc), &ajit1_intc_ops, intc,
                          "ajit1.intc", AJIT1_INTC_REG_MAP_SIZE);

    sysbus_init_mmio(sbd, &intc->iomem);
}

static const Property ajit1_intc_properties[] = {
    DEFINE_PROP_UINT32("ncpus", ajit1_intc_state, ncpus, 1),
};

static void ajit1_intc_class_init(ObjectClass *klass, const void *data)
{
    DeviceClass *dc = DEVICE_CLASS(klass);

    dc->realize = ajit1_intc_realize;
    device_class_set_legacy_reset(dc, ajit1_intc_reset);
    device_class_set_props(dc, ajit1_intc_properties);
}

static const TypeInfo ajit1_intc_info = {
    .name          = TYPE_AJIT1_INTC,
    .parent        = TYPE_SYS_BUS_DEVICE,
    .instance_size = sizeof(ajit1_intc_state),
    .class_init    = ajit1_intc_class_init,
};

static void ajit1_intc_register_types(void)
{
    type_register_static(&ajit1_intc_info);
}

type_init(ajit1_intc_register_types)
