/*
 * QEMU AJIT1 Timer Emulator
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
#include "hw/sysbus.h"
#include "qemu/timer.h"
#include "hw/irq.h"
#include "hw/ptimer.h"
#include "hw/qdev-properties.h"
#include "qemu/module.h"
#include "trace.h"
#include "qom/object.h"
#include "hw/timer/ajit1_timer.h"

OBJECT_DECLARE_SIMPLE_TYPE(AJIT1Timer, AJIT1_TIMER)

struct AJIT1Timer {
    SysBusDevice           parent_obj;

    MemoryRegion           iomem;

    struct ptimer_state    *ptimer;

    qemu_irq               irq;

    uint32_t               freq_hz;
    uint32_t               irq_line;
    uint32_t               count;

    /* registers */
    uint32_t               control;
};

/* Must be called within ptimer_transaction_begin/commit block */
static void ajit1_timer_enable(AJIT1Timer *timer)
{
    assert(timer != NULL);

    trace_ajit1_timer_enable();

    ptimer_stop(timer->ptimer);

    ptimer_set_count(timer->ptimer, (uint64_t)timer->count);
    ptimer_run(timer->ptimer, 1);
}

static void ajit1_timer_hit(void *opaque)
{
    AJIT1Timer *timer = opaque;
    assert(timer != NULL);

    trace_ajit1_timer_hit();

    /* Timer expired */
    if (timer->control & AJIT1_TIMER_ENABLE)
        qemu_irq_pulse(timer->irq);
}

static uint64_t ajit1_timer_read(void *opaque, hwaddr addr,
                                   unsigned size)
{
    AJIT1Timer *timer  = opaque;

    addr &= 0xff;

    /* AJIT1 Timer registers */
    switch (addr) {
    case AJIT1_TIMER_CTRL_OFFSET:
        trace_ajit1_timer_read(addr, timer->control, size);
        return timer->control;

    default:
        break;
    }

    trace_ajit1_timer_read(addr, 0, size);
    return 0;
}

static void ajit1_timer_write(void *opaque, hwaddr addr,
                                uint64_t value, unsigned size)
{
    AJIT1Timer *timer = opaque;

    addr &= 0xff;

    trace_ajit1_timer_write(addr, value, size);

    /* GPTimer registers */
    switch (addr) {
    case AJIT1_TIMER_CTRL_OFFSET:
        value &= 0xFFFFFFFF; /* clean up the value */
        if (value & AJIT1_TIMER_ENABLE) {
            ptimer_transaction_begin(timer->ptimer); 
            timer->control = value;
            timer->count = value >> 1;
            ajit1_timer_enable(timer);
            ptimer_transaction_commit(timer->ptimer);
        }
        return;

    default:
        break;
    }
}

static const MemoryRegionOps ajit1_timer_ops = {
    .read  = ajit1_timer_read,
    .write = ajit1_timer_write,
    .endianness = DEVICE_NATIVE_ENDIAN,
    .valid = {
        .min_access_size = 4,
        .max_access_size = 4,
    },
};

static void ajit1_timer_reset(DeviceState *d)
{
    AJIT1Timer *timer = AJIT1_TIMER(d);

    assert(timer != NULL);

    trace_ajit1_timer_reset();

    timer->control = 0; /* Disable timer */

    ptimer_transaction_begin(timer->ptimer);
    ptimer_stop(timer->ptimer);
    ptimer_set_count(timer->ptimer, 0);
    ptimer_set_freq(timer->ptimer, timer->freq_hz);
    ptimer_transaction_commit(timer->ptimer);
}

static void ajit1_timer_realize(DeviceState *dev, Error **errp)
{
    AJIT1Timer  *timer = AJIT1_TIMER(dev);
    SysBusDevice *sbd = SYS_BUS_DEVICE(dev);

    timer->ptimer = ptimer_init(ajit1_timer_hit, timer, PTIMER_POLICY_LEGACY);

    sysbus_init_irq(sbd, &timer->irq);

    ptimer_transaction_begin(timer->ptimer);
    ptimer_set_freq(timer->ptimer, timer->freq_hz);
    ptimer_transaction_commit(timer->ptimer);

    memory_region_init_io(&timer->iomem, OBJECT(timer), &ajit1_timer_ops,
                          timer, "ajit1.timer",
                          AJIT1_TIMER_REG_SIZE);

    sysbus_init_mmio(sbd, &timer->iomem);
}

static const Property ajit1_timer_properties[] = {
    DEFINE_PROP_UINT32("frequency", AJIT1Timer, freq_hz, 40000000),
    DEFINE_PROP_UINT32("irq-line",  AJIT1Timer, irq_line, 10),
};

static void ajit1_timer_class_init(ObjectClass *klass, const void *data)
{
    DeviceClass *dc = DEVICE_CLASS(klass);

    dc->realize = ajit1_timer_realize;
    device_class_set_legacy_reset(dc, ajit1_timer_reset);
    device_class_set_props(dc, ajit1_timer_properties);
}

static const TypeInfo ajit1_timer_info = {
    .name          = TYPE_AJIT1_TIMER,
    .parent        = TYPE_SYS_BUS_DEVICE,
    .instance_size = sizeof(AJIT1Timer),
    .class_init    = ajit1_timer_class_init,
};

static void ajit1_timer_register_types(void)
{
    type_register_static(&ajit1_timer_info);
}

type_init(ajit1_timer_register_types)
