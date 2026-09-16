/*
 * QEMU AJIT1 Interrupt Controller
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

#ifndef AJIT1_INTC_H
#define AJIT1_INTC_H

#include "hw/sysbus.h"

#define TYPE_AJIT1_INTC "ajit1-intc"

#define AJIT1_MAX_CPUS          0x4

#define AJIT1_INTC_MAX_CPU      AJIT1_MAX_CPUS
#define AJIT1_INTC_REG_MAP_SIZE 0x100      /* Size of memory mapped registers */

/* Memory mapped register offsets */

/*
 * AJIT1_INTC_CTRL_OFFSET(percpu & perthread) = 4*(2*cpu_id + thread_id)
 * Currently only working with cpu-0 and thread-0
*/

#define AJIT1_INTC_BASE_ADDR   (0xFFFF3000)
#define AJIT1_INTC_CTRL_OFFSET (0x00)

#define AJIT1_INTC_IPI_BASE    (0x80)
#define AJIT1_INTC_IPI_INTR_MASK AJIT1_INTC_IPI_BASE
#define AJIT1_INTC_IPI_INT_VAL   (AJIT1_INTC_IPI_BASE + 0x4)
#define AJIT1_INTC_IPI_MSG_HI(cpu) (AJIT1_INTC_IPI_BASE + 0x8 + 0x8 * cpu)
#define AJIT1_INTC_IPI_MSG_LO(cpu) (AJIT1_INTC_IPI_BASE + 0xc + 0x8 * cpu)
#define AJIT1_INTC_IPI_LOCK      (0xc8)

#define AJIT1_INTC_IPI_NR   11

#define AJIT1_INTC_MAX_PILS 16

void ajit1_intc_ack(DeviceState *dev, unsigned int cpu, int intno);

#endif /* AJIT1_INTC_H */
