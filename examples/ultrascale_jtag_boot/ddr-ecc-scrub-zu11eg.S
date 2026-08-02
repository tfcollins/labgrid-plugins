/*
 * Example ZynqMP DDR ECC scrub for the ADRV9009-ZU11EG memory map.
 *
 * Runs from OCM at 0xfffc0000 and initializes both 2 GiB banks described by
 * the production DT: [0, 0x80000000) and [0x800000000, 0x880000000).
 * Adapt both ranges for other boards; advertising unscrubbed ECC memory to
 * Linux causes an asynchronous SError during early memblock allocation.
 */
.section .text.boot, "ax"
.global _start
.global scrub_done
.type _start, %function
_start:
    msr daifset, #0xf
    mov x0, xzr
    movz x1, #0x8000, lsl #16
1:
    stp xzr, xzr, [x0, #0]
    stp xzr, xzr, [x0, #16]
    stp xzr, xzr, [x0, #32]
    stp xzr, xzr, [x0, #48]
    add x0, x0, #64
    cmp x0, x1
    b.lo 1b

    movz x0, #0x8, lsl #32
    movz x1, #0x8, lsl #32
    movk x1, #0x8000, lsl #16
2:
    stp xzr, xzr, [x0, #0]
    stp xzr, xzr, [x0, #16]
    stp xzr, xzr, [x0, #32]
    stp xzr, xzr, [x0, #48]
    add x0, x0, #64
    cmp x0, x1
    b.lo 2b
    dsb sy
scrub_done:
    wfe
    b scrub_done
.size _start, . - _start
