/*
 * QEMU AJIT1 UART
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

#ifndef AJIT1_UART_H
#define AJIT1_UART_H

#define TYPE_AJIT1_UART "ajit1-uart"

/* Size of memory mapped registers */
#define AJIT1_UART_REG_MAP_SIZE      0x100

/* Relevant AJI1 UART memory mapped register offsets */
#define AJIT1_UART_CONTROL_OFFSET    0x00
#define AJIT1_UART_TX_DATA_OFFSET    0x04
#define AJIT1_UART_RX_DATA_OFFSET    0x08

/* Relevant AJIT1 UART control register fields */
#define AJIT1_UART_TX_ENABLE         (1 <<  0)
#define AJIT1_UART_RX_ENABLE         (1 <<  1)
#define AJIT1_UART_RX_INTERRUPT      (1 <<  2)
#define AJIT1_UART_TX_FULL           (1 <<  3)
#define AJIT1_UART_RX_FULL           (1 <<  4)

#define AJIT1_UART_FIFO_LENGTH       1024


#endif
