/*
 * QEMU AJIT1 UART Emulator
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
#include "hw/qdev-properties-system.h"
#include "hw/sysbus.h"
#include "hw/irq.h"
#include "qemu/module.h"
#include "chardev/char-fe.h"
#include "qom/object.h"
#include "trace.h"
#include "hw/char/ajit1_uart.h"

OBJECT_DECLARE_SIMPLE_TYPE(ajit1_uart_state, AJIT1_UART)

struct ajit1_uart_state {
    SysBusDevice parent_obj;

    MemoryRegion iomem;

    qemu_irq irq;

    CharBackend chr;

    /* registers */
    uint32_t control;

    /* FIFO */
    char buffer[AJIT1_UART_FIFO_LENGTH];
    int  len;
    int  current;
};

static char ajit1_uart_pop(ajit1_uart_state *uart)
{
    char ret;

    if (uart->len == 0)
        return 0;

    ret = uart->buffer[uart->current++];

    if (uart->current >= uart->len) {
        /* Flush */
        uart->len     = 0;
        uart->current = 0;
    }

    return ret;
}

static void ajit1_uart_push(ajit1_uart_state *uart,
                            const uint8_t *buffer, int length)
{
    if (uart->len + length > AJIT1_UART_FIFO_LENGTH)
        abort();

    memcpy(uart->buffer + uart->len, buffer, length);
    uart->len += length;
}

static int ajit1_uart_can_receive(void *opaque)
{
    ajit1_uart_state *uart = opaque;

    return AJIT1_UART_FIFO_LENGTH - uart->len;
}

static void ajit1_uart_receive(void *opaque, const uint8_t *buf, int size)
{
    ajit1_uart_state *uart = opaque;

    if (uart->control & AJIT1_UART_RX_ENABLE) {
        ajit1_uart_push(uart, buf, size);
        uart->control |= AJIT1_UART_RX_FULL;
        if(uart->control & AJIT1_UART_RX_INTERRUPT)
            qemu_irq_pulse(uart->irq);
    }
}

static uint64_t ajit1_uart_read(void *opaque, hwaddr addr, unsigned size)
{
    ajit1_uart_state *uart = opaque;
    uint64_t val = 0;

    addr &= 0xFF;

    /* Unit registers */
    switch (addr) {
    case AJIT1_UART_RX_DATA_OFFSET:
    /* when only one byte read */
    case AJIT1_UART_RX_DATA_OFFSET + 3:
        val = ajit1_uart_pop(uart);
        /* Keep RX_FULL set while the FIFO still holds bytes so the guest
         * can drain a multi-byte receive in one interrupt.
         */
        if (uart->len == 0)
            uart->control &= ~AJIT1_UART_RX_FULL;
        else
            uart->control |= AJIT1_UART_RX_FULL;
        break;

    case AJIT1_UART_CONTROL_OFFSET:
        val = uart->control;
        break;

    default:
        val = 0;
        break;
    }
    trace_ajit1_uart_read(addr, val, size);
    return val;
}

static void ajit1_uart_write(void *opaque, hwaddr addr,
                                uint64_t value, unsigned size)
{
    ajit1_uart_state *uart = opaque;
    unsigned char c = 0;

    addr &= 0xFF;

    trace_ajit1_uart_write(addr, value, size);

    /* Unit registers */
    switch (addr) {
    case AJIT1_UART_TX_DATA_OFFSET:
    /* when only one byte write */
    case AJIT1_UART_TX_DATA_OFFSET + 3:
        /* Transmit when character device available and transmitter enabled */
        uart->control |= AJIT1_UART_TX_FULL;
        if (qemu_chr_fe_backend_connected(&uart->chr) &&
            (uart->control & AJIT1_UART_TX_ENABLE)) {
            c = value & 0xFF;
            /* This blocks entire thread. Rewrite to use
             * qemu_chr_fe_write and background I/O callbacks */
            qemu_chr_fe_write_all(&uart->chr, &c, 1);
            uart->control &= ~AJIT1_UART_TX_FULL;
        }
        return;

    case AJIT1_UART_CONTROL_OFFSET:
        uart->control = value;
        return;

    default:
        break;
    }
}

static const MemoryRegionOps ajit1_uart_ops = {
    .write      = ajit1_uart_write,
    .read       = ajit1_uart_read,
    .endianness = DEVICE_NATIVE_ENDIAN,
};

static void ajit1_uart_realize(DeviceState *dev, Error **errp)
{
    ajit1_uart_state *uart = AJIT1_UART(dev);
    SysBusDevice *sbd = SYS_BUS_DEVICE(dev);

    qemu_chr_fe_set_handlers(&uart->chr,
                             ajit1_uart_can_receive,
                             ajit1_uart_receive,
                             NULL,
                             NULL, uart, NULL, true);

    sysbus_init_irq(sbd, &uart->irq);

    memory_region_init_io(&uart->iomem, OBJECT(uart), &ajit1_uart_ops, uart,
                          "ajit1.uart", AJIT1_UART_REG_MAP_SIZE);

    sysbus_init_mmio(sbd, &uart->iomem);
}

static void ajit1_uart_reset(DeviceState *d)
{
    ajit1_uart_state *uart = AJIT1_UART(d);

    /* Everything is off */
    uart->control = 0;

    /* Flush receive FIFO */
    uart->len = 0;
    uart->current = 0;
}

static const Property ajit1_uart_properties[] = {
    DEFINE_PROP_CHR("chrdev", ajit1_uart_state, chr),
};

static void ajit1_uart_class_init(ObjectClass *klass, const void *data)
{
    DeviceClass *dc = DEVICE_CLASS(klass);

    dc->realize = ajit1_uart_realize;
    device_class_set_legacy_reset(dc, ajit1_uart_reset);
    device_class_set_props(dc, ajit1_uart_properties);
}

static const TypeInfo ajit1_uart_info = {
    .name          = TYPE_AJIT1_UART,
    .parent        = TYPE_SYS_BUS_DEVICE,
    .instance_size = sizeof(ajit1_uart_state),
    .class_init    = ajit1_uart_class_init,
};

static void ajit1_uart_register_types(void)
{
    type_register_static(&ajit1_uart_info);
}

type_init(ajit1_uart_register_types)
