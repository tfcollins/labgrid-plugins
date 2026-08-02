/*
 * ZynqMP JTAG production-boot handoff.
 *
 * Enter a raw U-Boot binary at 0x08000000 as non-secure AArch64 EL2. This
 * replaces BL31 only for the recovery case where the physical boot straps are
 * fixed to JTAG. PS initialization and PMU firmware startup remain the
 * responsibility of XilinxJTAGDriver.load_zynqmp_production_uboot().
 */
.section .text.boot, "ax"
.global _start
.type _start, %function
_start:
    msr daifset, #0xf

    /* Non-secure AArch64 below EL3; permit HVC. */
    movz x4, #0x501
    msr scr_el3, x4

    /* AArch64 EL2 with translation and caches initially disabled. */
    movz x4, #0x8000, lsl #16
    msr hcr_el2, x4
    movz x4, #0x3
    msr cnthctl_el2, x4
    msr cntvoff_el2, xzr
    msr sctlr_el2, xzr

    /* FSBL normally copies IOU CNTFID0 into CNTFRQ_EL0. */
    movz x4, #0xa054
    movk x4, #0x01fc, lsl #16 /* 33,333,332 Hz */
    msr cntfrq_el0, x4

    /*
     * BL31 normally assigns the GICv2 SGIs, PPIs, and platform SPIs to the
     * non-secure world. Without this, production U-Boot runs only until it
     * starts using interrupts and then falls back into an EL3 exception path.
     */
    movz x5, #0x0000
    movk x5, #0xf901, lsl #16    /* GICD_CTLR */
    str wzr, [x5]
    dsb sy
    add x8, x5, #0x80           /* GICD_IGROUPR0 */
    mov w6, #0xffffffff
    mov x7, #8
1:
    str w6, [x8], #4
    subs x7, x7, #1
    b.ne 1b
    mov w6, #3                  /* EnableGrp0 + EnableGrp1 */
    str w6, [x5]
    dsb sy

    movz x5, #0x0000
    movk x5, #0xf902, lsl #16   /* GICC_CTLR */
    mov w6, #0xff
    str w6, [x5, #4]            /* GICC_PMR */
    mov w6, #3
    str w6, [x5]                /* GICC_CTLR */
    dsb sy

    /* U-Boot entry has no firmware argument block. */
    mov x0, xzr
    mov x1, xzr
    mov x2, xzr
    mov x3, xzr

    /* EL2h, DAIF masked, production U-Boot at 0x08000000. */
    movz x4, #0x3c9
    msr spsr_el3, x4
    movz x4, #0x0800, lsl #16
    msr elr_el3, x4
    dsb sy
    isb
    eret
.size _start, . - _start
