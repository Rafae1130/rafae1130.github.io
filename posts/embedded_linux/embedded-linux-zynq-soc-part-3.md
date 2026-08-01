# Embedded Linux (Zynq SoC): Part 3 - Device Tree Overlay and UIO

*This is Part 3 of the Embedded Linux ([Zynq SoC](https://www.amd.com/en/products/adaptive-socs-and-fpgas/soc/zynq-7000.html)) series. Read [Part 1](https://rafae1130.github.io/posts/embedded_linux/embedded-linux-zynq-soc-part-1.html) and [Part 2: Device Tree](https://rafae1130.github.io/posts/embedded_linux/embedded-linux-zynq-soc-part-2.html) if you haven't already.*

## Table of contents

1. [Introduction](#sec-1)
2. [Block Diagram](#sec-2)
3. [What is UIO?](#sec-3)
4. [Interrupt Flow (Hardware to Userspace)](#sec-4)
5. [What is a Device Tree Overlay?](#sec-5)
6. [The Overlay](#sec-6)
   - [How the interrupt number is calculated](#sec-irq-calc)
7. [The C Application](#sec-7)
8. [On the Board](#sec-8)
9. [Summary](#sec-9)
10. [What's Next](#sec-10)

# **1\. Introduction** {#sec-1}

In [Parts 1](https://rafae1130.github.io/posts/embedded_linux/embedded-linux-zynq-soc-part-1.html) and [2](https://rafae1130.github.io/posts/embedded_linux/embedded-linux-zynq-soc-part-2.html) we have been through enough theory. Now it is time to do something practical. In this blog we will learn about [device tree overlays](https://docs.kernel.org/devicetree/overlay-notes.html): when and how to use them, what [UIO](https://docs.kernel.org/driver-api/uio-howto.html) is, when and how to use it, and walk through the steps with a final test on a Xilinx [Zybo](https://digilent.com/reference/programmable-logic/zybo/start) board.

In this example, we'll build a simple GPIO peripheral connected to buttons on the board in the FPGA and access it from a userspace application without writing a kernel driver. The button presses will generate an interrupt which we will detect in the software.

To make that work we need three things:

* a **device tree overlay** so Linux knows the hardware exists,  
* **UIO** so the registers and interrupts are exposed to userspace,  
* and a simple C application that waits for button interrupts.

# **2\. Block Diagram** {#sec-2}

Here is the [Vivado](https://www.amd.com/en/products/software/adaptive-socs-and-fpgas/vivado.html) block design used for this example.

![][image1]

**Figure 1: Zynq PS + AXI GPIO buttons, interrupt wired to IRQ_F2P.**

What each block is doing (one line each):

* **ZYNQ7 Processing System**: [Zynq](https://en.wikipedia.org/wiki/Zynq) PS (ARM cores + interrupt controller).  
* **AXI SmartConnect**: [AXI](https://www.arm.com/architecture/system-architectures/amba/amba-5) interconnect between the PS and the GPIO.  
* **AXI GPIO**: memory-mapped GPIO for the buttons; also generates an interrupt when an input changes ([PG144](https://docs.amd.com/r/en-US/pg144-axi-gpio)).  
* **btns_4bits**: the four board buttons.  
* **Concat**: packs the GPIO interrupt onto bit 0 of `IRQ_F2P`.  
* **Constant**: ties the unused `IRQ_F2P` bits to 0.  
* **Processing System Reset**: reset for the AXI / PL logic.

The focus of this blog is UIO, device tree overlay, and interrupt handling, so we will not go into much detail about the FPGA design itself. You do not need this exact block design. Any AXI GPIO wired to a Zynq `IRQ_F2P` line works the same way. If you use a different PL interrupt pin, the device-tree interrupt number changes with it. For example, `IRQ_F2P[0]` becomes SPI `29` in the overlay, while `IRQ_F2P[1]` becomes SPI `30` (hardware IRQ `62`, then `62 − 32`).

Simply what this design does is:

* PS talks to AXI GPIO over AXI (read button state, enable interrupt registers).  
* Button change → `ip2intc_irpt` → Concat → `IRQ_F2P[0]` → [GIC](https://developer.arm.com/documentation/ihi0048/latest/) → Linux.

# **3\. What is UIO?** {#sec-3}

**[UIO](https://docs.kernel.org/driver-api/uio-howto.html)** stands for **Userspace I/O**. It is a kernel framework including a kernel driver (`uio_pdrv_genirq`) which provides functionality like interrupt handling and MMIO access.

Normally, hardware peripherals are controlled by kernel drivers. But for simple FPGA IPs, writing a complete driver is often unnecessary. In many cases, you only need to:

* Access the peripheral's registers.  
* Receive an interrupt when an event occurs.

That's exactly what UIO provides.

UIO divides the work between the kernel and your userspace application. The kernel handles tasks that require privileged access, while the application implements the device-specific logic.

**Kernel (UIO driver)**

* Claims and manages the interrupt.  
* Creates the `/dev/uioX` device.  
* Maps the peripheral's registers so they can be accessed using `mmap()`.  
* Wakes the application when an interrupt occurs.

**Userspace application**

* Opens `/dev/uioX`.  
* Maps the peripheral registers with `mmap()`.  
* Waits for an interrupt by sleeping on `read()`. The process is free to work on other threads. 
* Processes the interrupt event.  
* Clears the interrupt in the peripheral.  
* Calls `write()` to tell the UIO driver to re-enable future interrupts.

This split keeps the kernel driver generic and very small, while allowing the application to contain all of the device-specific functionality. Instead of writing a custom kernel driver for every simple FPGA peripheral, only the minimal interrupt and memory-management code runs in the kernel, with the rest of the logic implemented in userspace.

### **When should you use UIO?**

UIO is a good choice when:

* Your peripheral is a simple memory-mapped (MMIO) IP.  
* Most of the logic can live in a userspace application.  
* You only need register access and basic interrupt handling.

If the hardware needs tight kernel integration, must be shared between multiple processes, or interacts with kernel subsystems such as networking or storage, then a full kernel driver is the better choice.

# **4\. Interrupt Flow (Hardware to Userspace)** {#sec-4}

Why not just poll the GPIO data register in a loop?

* Polling wastes CPU time and still misses short presses unless you poll very fast.  
* An interrupt wakes the CPU only when something actually happened.

So for a button, interrupt is the natural choice. AXI GPIO can raise `ip2intc_irpt` on every input change (press **and** release).

With UIO, the path from the FPGA pin to your app looks like this:

```text
FPGA hardware
      |
      | IRQ signal
      v
UIO driver (kernel)
      |
      | wakes thread blocked in read()
      v
Your userspace application
```

What each step means:

1. **FPGA hardware**: button edge hits AXI GPIO; the IP asserts `ip2intc_irpt`, which is wired to `IRQ_F2P[0]` into the Zynq GIC.  
2. **UIO driver (kernel)**: the GIC delivers that IRQ to Linux and the registered UIO handler (`uio_pdrv_genirq`) runs. It does **not** run your application logic in kernel space. It records that an interrupt happened and disables the IRQ line until userspace re-enables it.  
3. **Your userspace application**: if your process was blocked in `read("/dev/uio0")`, that `read` returns. Your app wakes up, clears the hardware status in mapped registers, then `write()`s back to UIO so the next IRQ can be delivered.

# **5\. What is a Device Tree Overlay?** {#sec-5}

In [Part 2](https://rafae1130.github.io/posts/embedded_linux/embedded-linux-zynq-soc-part-2.html), we learned that the [device tree](https://www.devicetree.org/) is loaded during boot and tells Linux what hardware is present on the board. Once the kernel has booted, that hardware description is fixed.

With [PetaLinux](https://docs.amd.com/r/en-US/ug1144-petalinux-tools-reference-guide), however, the FPGA can be reprogrammed while Linux is already running using the [FPGA Manager](https://docs.amd.com/r/en-US/ug1144-petalinux-tools-reference-guide/FPGA-Manager-Configuration-and-Usage-for-Zynq-7000-Devices-and-Zynq-UltraScale-MPSoC) and tools such as [`fpgautil`](https://xilinx-wiki.atlassian.net/wiki/spaces/A/pages/18841847). The new [bitstream](https://docs.amd.com/r/en-US/ug470_7Series_Config) may introduce new PL peripherals, such as a custom AXI IP or GPIO, that were not present when Linux booted.

At this point, Linux has a problem. New hardware now exists on the FPGA, but Linux has no knowledge of it. It does not know the newly added peripheral's address, interrupt, or which driver should manage it.

A [device tree overlay](https://docs.kernel.org/devicetree/overlay-notes.html) solves this problem. It is a small device tree fragment that is applied on top of the existing device tree, adding or updating only the nodes needed for the newly loaded hardware. Instead of replacing the entire device tree, the overlay simply patches the parts that have changed.

### Why not rebuild the entire device tree?

You certainly can. You could update the full device tree, rebuild the image, and reboot the system. However, for a small change in the FPGA design, this is unnecessary work.

A device tree overlay contains exactly the same information as a normal device tree node, such as `compatible`, `reg`, and `interrupts`, but only for the new hardware. This allows Linux to recognize and use the newly programmed FPGA peripherals without rebuilding or rebooting the system.

# **6\. The Overlay** {#sec-6}

This is the overlay used for the button GPIO + UIO:

```dts
/dts-v1/;
/plugin/;

&amba {
    #address-cells = <1>;
    #size-cells = <1>;

    axi_gpio_uio@41200000 {
        compatible = "generic-uio";
        status = "okay";
        reg = <0x41200000 0x10000>;
        interrupt-parent = <&intc>;
        interrupts = <0 29 4>;
    };
};
```

* **`/dts-v1/;`**: marks this as device tree source.  
* **`/plugin/;`**: marks this file as an **overlay** (not a complete tree).  
* **`&amba { ... }`**: which parent node in the base device tree this overlay node belongs under. On many Zynq / PetaLinux trees the label `amba` points at `/axi`. Check your base DTS (or `/proc/device-tree`) for the real label; some trees use `&axi` instead. Same idea for `&intc`: it must be the label of your GIC node in the base tree.  
* **`#address-cells` / `#size-cells`**: must match the parent bus (usually `<1>` / `<1>` on Zynq `amba` / `axi`).  
* **`axi_gpio_uio@41200000`**: new device node. The name before `@` can be anything sensible; the `@41200000` should match the MMIO base so the unit address stays consistent with `reg`.  
* **`compatible = "generic-uio"`**: which driver should bind. Here we want UIO (`uio_pdrv_genirq` with `of_id=generic-uio`).  
* **`status = "okay"`**: this device is enabled.  
* **`reg = <0x41200000 0x10000>`**: MMIO window: base and size from Vivado’s Address Editor. This is what userspace will `mmap` through UIO.  
* **`interrupt-parent = <&intc>`**: interrupt controller is the Zynq GIC node already present in the base tree.  
* **`interrupts = <0 29 4>`**: explained in detail below.

The base address and range come from Vivado Address Editor (Window → Address Editor), not from guessing:

![][image11]

**Figure 2: Address Editor, AXI GPIO mapped at `0x41200000`, range 64K (`0x10000`).**

Here `Master Base Address` is `0x41200000` and `Range` is `64K`, which is `0x10000` bytes. That is why `reg` uses those two values even though the GPIO only has a handful of useful registers; the bus mapping is allocated in a 64K window. If your design shows a different base, put that base in both `@...` and `reg`.

Why `reg` if we only care about the interrupt?

* UIO uses `reg` to create the MMIO mapping for `/dev/uio0`. Without it there is nothing to `mmap`, so userspace cannot touch the GPIO at all, not even to enable interrupts or read which button was pressed.  
* That same mapping is also how the app clears `IPISR` after each IRQ so the level interrupt can drop and the next press can fire again.

## How the interrupt number is calculated (`29` and the −32) {#sec-irq-calc}

The line:

```dts
interrupts = <0 29 4>;
```

is three cells for a GIC:

| Cell | Value | Meaning |
|------|-------|---------|
| 1 | `0` | Shared Peripheral Interrupt (SPI), not a PPI |
| 2 | `29` | SPI index |
| 3 | `4` | IRQ type: level-high (matches AXI GPIO `ip2intc_irpt`) |

The interesting one is `29`. It does **not** appear directly in Vivado as "29". You get it from the Zynq PL→PS interrupt map plus how Linux / device tree number GIC SPIs.

From the [Zynq-7000 TRM](https://docs.amd.com/r/en-US/ug585-zynq-7000-SoC-TRM) (PL interrupt signals):

![][image3]

**Figure 3: PL interrupt signals into the PS / GIC (Zynq-7000).**

For our design we use `IRQ_F2P[0]` (also written `IRQF2P[0]`):

* Table row: `IRQF2P[7:0]` → SPI / IRQ IDs `[68:61]`  
* So bit 0 maps to hardware interrupt ID **61**  
* In general: `IRQ_F2P[n]` → hardware ID `61 + n` for `n = 0..7`

`/proc/interrupts` on Linux will also show **61** for this line once the overlay is applied. That is the GIC hardware ID.

Device tree does **not** put `61` in the second cell. For ARM GICs, the device tree SPI number is:

```text
DT SPI number = GIC hardware IRQ ID − 32
```

So:

```text
IRQ_F2P[0]  →  hardware ID 61
61 − 32    →  29
interrupts = <0 29 4>;
```

If the GPIO interrupt were wired to `IRQ_F2P[1]` instead, the hardware ID would be `62` and the overlay would use `interrupts = <0 30 4>;` (`62 − 32 = 30`). The rest of the node stays the same.

### Where does the −32 come from?

The [ARM GIC](https://developer.arm.com/documentation/ihi0048/latest/) interrupt ID space is split into bands:

| ID range | Name | What it is |
|----------|------|------------|
| 0–15 | SGI | Software Generated Interrupts |
| 16–31 | PPI | Private Peripheral Interrupts (per CPU) |
| 32+ | SPI | Shared Peripheral Interrupts (shared across CPUs) |

SPI hardware IDs therefore start at **32**. The device tree binding for the GIC does not store the full hardware ID in the SPI cell. It stores the **SPI index**: how far that interrupt is past the start of the SPI range:

```text
SPI index = hardware ID − 32
         = 61 − 32
         = 29
```

Linux then turns that back into hardware ID 61 when it programs the GIC. That is why:

* the **overlay** says `29`  
* `/proc/interrupts` shows `GIC-0 61`

# **7\. The C Application** {#sec-7}

Goal of the app:

* enable AXI GPIO interrupt  
* block until a button IRQ  
* print which button  
* clear status and arm again  
* ignore the release edge (AXI GPIO interrupts on press **and** release)

These are the AXI GPIO registers we care about (offsets from the IP base address):

![][image4]

**Figure 4: AXI GPIO register map.**

Notes that matter for the app:

* Interrupt registers (`GIER`, `IP IER`, `IP ISR`) exist only if **Enable Interrupt** was turned on in the AXI GPIO IP.  
* `IP ISR` is toggle-on-write: writing `1` to a set bit clears that pending interrupt.  
* Offsets are relative to the base in `reg` (`0x41200000` in our overlay).

### Register offsets

```c
#define MAP_SIZE   0x10000
#define GPIO_DATA  (0x000 / 4)
#define GPIO_GIER  (0x11C / 4)
#define GPIO_IPISR (0x120 / 4)
#define GPIO_IPIER (0x128 / 4)
```

The datasheet lists offsets in **bytes** (`0x11C`, `0x120`, …). We map the registers as a `uint32_t *`, so each index steps by 4 bytes. Dividing by 4 converts a byte offset into an array index: `gpioRegs[0x11C / 4]` is the same as “base + 0x11C”.  
`MAP_SIZE` matches the overlay `reg` size (`0x10000`).

### Open UIO and map registers

```c
int uioFd = open("/dev/uio0", O_RDWR);

volatile uint32_t *gpioRegs = mmap(NULL, MAP_SIZE,
    PROT_READ | PROT_WRITE, MAP_SHARED, uioFd, 0);
```

* `open`: attach to the UIO device created when the overlay binds.  
* `mmap`: map the GPIO MMIO window (`0x41200000`, size `0x10000`) into this process.  
* After this, `gpioRegs[offset]` is a normal pointer read/write to PL registers.

### Enable interrupts (GPIO + UIO)

```c
uint32_t irqEnable = 1;

gpioRegs[GPIO_IPIER] = 1;          /* channel 1 IRQ enable */
gpioRegs[GPIO_GIER]  = 0x80000000; /* global IRQ enable */
gpioRegs[GPIO_IPISR] = 1;          /* clear any pending */

write(uioFd, &irqEnable, sizeof(irqEnable));  /* allow UIO to deliver IRQs */
```

AXI GPIO interrupt enables are two levels:

* **IP IER (`0x128`)**: per-channel enable inside the GPIO IP. Writing `1` enables channel 1 (the button channel in this design). If this bit is 0, a button edge does not set the IP interrupt output.  
* **GIER (`0x11C`)**: global interrupt enable for the whole IP. Bit 31 is the enable bit, so the value is `0x80000000`. If GIER is 0, no interrupt leaves the GPIO even when IPIER is set.

Without both, AXI GPIO never asserts `ip2intc_irpt`. Clearing IPISR drops any stale pending status before we start waiting. `write()` tells UIO it may deliver the next interrupt to userspace.

### Main loop: wait, handle, re-arm

```c
printf("Press a button...\n");
fflush(stdout);

while (1) {
    read(uioFd, &irqEnable, sizeof(irqEnable)); /* block until IRQ */

    gpioRegs[GPIO_IPIER] = 0;                   /* mask while bouncing */
    usleep(20000);

    uint32_t buttonValue = gpioRegs[GPIO_DATA] & 0xF;

    gpioRegs[GPIO_IPISR] = 1;                   /* clear HW status */
    gpioRegs[GPIO_IPIER] = 1;                   /* unmask GPIO IRQ */

    irqEnable = 1;
    write(uioFd, &irqEnable, sizeof(irqEnable)); /* re-enable UIO */

    if (buttonValue) {
        int i;
        for (i = 0; i < 4; i++) {
            if (buttonValue & (1u << i)) {
                printf("Button = %d\n", i + 1); /* bit0 -> 1 ... bit3 -> 4 */
                fflush(stdout);
            }
        }
    }
}
```

* `read`: sleeps until the IRQ fires. Other threads can still run while this one blocks.  
* mask + `usleep`: buttons bounce; briefly ignore extra edges.  
* read DATA: bitmask of which button(s) are down (`bit0` = button 1, …, `bit3` = button 4).  
* clear IPISR: required for a level IRQ; skip this and you get an interrupt storm.  
* `write` again: UIO disables the IRQ when it fires; re-enable for the next press.  
* `if (buttonValue)`: press and release both interrupt. Idle is `0`, so print only on press. Each set bit prints as `Button = 1` … `4`.

# **8\. On the Board** {#sec-8}

Do these in order: load UIO with `of_id`, then program the bitstream, then apply the overlay, then run the app.

## Compile the device tree overlay

```bash
dtc -I dts -O dtb -o axi_gpio_uio.dtbo axi_gpio_uio.dts
```

![][image12]

<div class="tip-box" markdown="1">

**Compile tip.** `#address-cells` / `#size-cells` must match the parent bus. For Zynq `amba` / `axi` that is usually `<1>` and `<1>`. They are not strictly required for the overlay to work on the board, but if you omit them `dtc` falls back to defaults (`#address-cells = 2`) and you get `reg_format` warnings like these:

![][image2]

</div>

Copy `axi_gpio_uio.dtbo` onto the board.

## Convert FPGA `.bit` to `.bit.bin`

Latest version of [PetaLinux](https://docs.amd.com/r/en-US/ug1144-petalinux-tools-reference-guide) requires a `.bit.bin` version of bitstream instead of just `.bit`. This `.bit` can be converted to `.bit.bin` using the `bootgen` tool available in PetaLinux.

Create a `.bif` file first:

![][image5]

Run after sourcing PetaLinux:

![][image6]

Make sure the `.bit` file is present in same directory where the command is being run from.

## Load the UIO driver

```bash
sudo modprobe uio_pdrv_genirq of_id=generic-uio
```

### **Why is of_id required?**

Our overlay contains:

```dts
compatible = "generic-uio";
```

Normally, a kernel driver already contains a list of compatible strings that it supports that it matches with the compatible string in the device tree node. When Linux finds a matching node in the device tree, it automatically binds the driver.

But `uio_pdrv_genirq` driver is different. It does not hardcode any compatible strings. I'm not sure what the reason for this is. I think its just a design choice of author. So when loading the module you have to tell it which compatible string to look for in the dt node.

```bash
sudo modprobe uio_pdrv_genirq of_id=generic-uio
```

![][image7]

This tells the driver to bind to any device tree node whose compatible property is `"generic-uio"`.

Check with `lsmod` (lists kernel modules that are currently loaded).

## Apply the overlay

Load the bitstream:

```bash
sudo fpgautil -b <.bit.bin name>
```

![][image8]

Load the device tree overlay:

```bash
sudo fpgautil -o axi_gpio_uio.dtbo
```

![][image13]

## Check the interrupt / device

```bash
ls -l /dev/uio0
grep axi_gpio /proc/interrupts
```

You should see something like:

![][image9]

## Run the application

Cross-compile on the host using arm cross compiler(available in Petalinux), copy the binary to the board, then:

```bash
sudo ./uio_btn
```

Press a button. You should get one line per press, for example:

![][image10]

# **9\. Summary** {#sec-9}

* Vivado: buttons → AXI GPIO → `IRQ_F2P[0]`.  
* Overlay: tells Linux the MMIO (`reg`), the IRQ, and `compatible = "generic-uio"`.  
* Interrupt number: hardware ID `61` → DT SPI `29` because SPI IDs start at 32 (`61 − 32`).  
* UIO: kernel owns the IRQ line; your app owns the policy.  
* `of_id` must match `compatible`, or the driver never binds.  
* App: `read` to wait, clear GPIO status, `write` to re-arm, ignore release.

In [Part 2](https://rafae1130.github.io/posts/embedded_linux/embedded-linux-zynq-soc-part-2.html) the device tree described what exists. Here we showed how to **add** a PL peripheral at runtime and drive its interrupt from userspace.

# **10\. What's Next** {#sec-10}

Next we can look at doing the same path with a small in-kernel IRQ handler instead of [UIO](https://docs.kernel.org/driver-api/uio-howto.html), and compare when each approach makes sense.

---

**Series:** [Part 1](https://rafae1130.github.io/posts/embedded_linux/embedded-linux-zynq-soc-part-1.html) · [Part 2: Device Tree](https://rafae1130.github.io/posts/embedded_linux/embedded-linux-zynq-soc-part-2.html) · Part 3


[image1]: images/image1_p3.png
[image2]: images/image2_p3.png
[image3]: images/image3_p3.png
[image4]: images/image4_p3.png
[image5]: images/image5_p3.png
[image6]: images/image6_p3.png
[image7]: images/image7_p3.png
[image8]: images/image8_p3.png
[image9]: images/image9_p3.png
[image10]: images/image10_p3.png
[image11]: images/image11_p3.png
[image12]: images/image12_p3.png
[image13]: images/image13_p3.png
