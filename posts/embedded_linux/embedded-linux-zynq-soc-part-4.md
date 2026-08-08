# Embedded Linux (Zynq SoC): Part 4 - Linux Device Drivers

*This is Part 4 of the Embedded Linux ([Zynq SoC](https://www.amd.com/en/products/adaptive-socs-and-fpgas/soc/zynq-7000.html)) series. Read [Part 1](https://rafae1130.github.io/posts/embedded_linux/embedded-linux-zynq-soc-part-1.html), [Part 2: Device Tree](https://rafae1130.github.io/posts/embedded_linux/embedded-linux-zynq-soc-part-2.html) and [Part 3: Device Tree Overlay and UIO](https://rafae1130.github.io/posts/embedded_linux/embedded-linux-zynq-soc-part-3.html) if you haven't already.*

In [Part 3](https://rafae1130.github.io/posts/embedded_linux/embedded-linux-zynq-soc-part-3.html) we used [UIO](https://docs.kernel.org/driver-api/uio-howto.html) and a device tree overlay to reach a custom PL IP from a userspace application. We mapped the registers and detected the interrupts using UIO driver.

All the code we wrote was in userspace and our application interected with the UIO driver already provided in the kernel.

UIO is enough when we just want MMIO register access or interrupts detection. In this blog we look at when UIO is not enough, and we build and understand the required basics to start writing our own kernel driver in the next blog.

## Table of contents

1. [When UIO is not enough](#sec-1)
2. [Userspace and kernel space](#sec-2)
3. [Why the vendor writes the driver](#sec-3)
4. [Two views of Linux device drivers](#sec-4)
5. [File operations: what the application sees](#sec-5)
6. [The platform driver](#sec-6)
   - [6.1 The skeleton](#sec-6-1)
   - [6.2 imgproc_of_match: how Linux finds the driver](#sec-6-2)
   - [6.3 struct imgproc: what the driver remembers](#sec-6-3)
   - [6.4 imgproc_probe: getting the IP ready](#sec-6-4)
   - [6.5 imgproc_open and imgproc_release](#sec-6-5)
   - [6.6 imgproc_ioctl](#sec-6-6)
   - [6.7 imgproc_write and imgproc_read](#sec-6-7)
   - [6.8 imgproc_poll and imgproc_isr](#sec-6-8)
   - [6.9 imgproc_remove](#sec-6-9)
7. [Summary](#sec-7)
8. [What's Next](#sec-8)
9. [References](#sec-9)

# **1\. When UIO is not enough** {#sec-1}

[UIO](https://docs.kernel.org/driver-api/uio-howto.html) gave us two things: access to the registers, and a way to wait for the interrupt. For the example in [Part 3](https://rafae1130.github.io/posts/embedded_linux/embedded-linux-zynq-soc-part-3.html) that was all we needed.

However, UIO is not enough in the following cases cases:

* **DMA.** The IP moves data by itself instead of the CPU copying it, so it needs memory and buffers allocation/management, which UIO doesn't provide and userspace application doesnt have access to large contiguos memory.
* **Cache coherency.** The IP doesnt know the data its reading is from cache or stale data in DRAM. For cache coherancy, kernel driver is required.
* **More than one process.** If two applications try to access the same IP through UIO, it cannot provide arbitration, if there are going to be multiple userspace application running at same time accessing hte same IP, kernel driver is required.

<div class="tip-box" markdown="1">

**Note.** You can do DMA from userspace, and people do: reserve a region of memory at boot, map it through `/dev/mem`, and give that fixed physical address to the IP. It works, but you need root access for this, the memory is carved out of the system whether you use it or not, and a wrong address writes over anything. The kernel has a proper way to do this, which is the [DMA API](https://docs.kernel.org/core-api/dma-api.html).

</div>


# **2\. Userspace and kernel space** {#sec-2}

Whenever you write an application and run it, it runs in userspace. It gets its own virtual address space, it cannot touch physical memory directly.

A driver runs in kernel space, so it can do things an application cannot:

* map the IP registers and provide access of those registers to userspace without userspace being aware of physical address.
* own the interrupt line, run a function when it fires, and wake up the process that was waiting for it
* allocate memory the IP can reach, and keep the caches correct
* decide whether a second process may open the device while the first still has it

![][image2]

**Figure 2: How one call reaches the IP. The application calls ioctl(), our imgproc_ioctl() runs in the kernel, and that writes the register in the IP.**

The downside is that mistakes are worse.

A bad pointer in an application is a segfault in that one process. In a driver it can take down the board.

# **3\. Why the vendor writes the driver** {#sec-3}

If we build an image processing IP and sell it. We have to ship software that talks to the IP with it (if its an SOC system).

But we cannot ship the userspace application, because we do not know what the customer is building. One customer can stream data from camera and another processes camera files from disk. Both require different userspace applications.

So we provide the driver instead. Which is hides the hardware and provides a simple software interface to talk to it. 
add an example here......
The customer can use this to talk to the hardware according to the required usecase which knowing details about the hardware itself.


# **4\. Two views of Linux device drivers** {#sec-4}

There are two separate questions about any driver. What does it look like to the application, and how did Linux find the hardware?

![][image3]

**Figure 3: The two views, and where our PL IP lands in each of them.**

### Why can PCIe and USB be enumerated?

By enumeration it means that the kernel can find out whats connected to its bus when we connect it. We dont have to provide information in the device tree beforehand. It is because the when the linux asks what is connected on the bus, the device answers with its information, i.e. registers, interrupts. the information that we provide in device tree for non-enumerable devices.

[AXI](https://www.arm.com/architecture/system-architectures/amba/amba-5) has no such thing. If we read an address where no IP is mapped, we do not get an answer saying nothing is here. We get a bus error, or the read hangs.

So a PL IP on AXI cannot be discovered this way. The [Device Tree](https://www.devicetree.org/) describes it to Linux instead, and Linux  represent these as a [platform device](https://docs.kernel.org/driver-api/driver-model/platform.html) for each IP it finds there.


# **5\. Userspace applicatoin interface** {#sec-5}

The driver creates a file in `/dev`. The application opens that file and uses normal file calls on it such as read write.

These calls are our interface to the driver, and through the driver, to the IP.

The names of these calls are fixed, but what they do is up to us. We will use our image processing IP as the example.

### open and release

`open` is the first step to talk to the hardware. As we have to open a file before doing any file operations, similarly, since these character devices are represented as a file, we have to open it to begin talking to it.

`open` gives back a file descriptor, and every call after that uses it. That file descriptor is our connection to the driver, and through the driver, to the IP.

```c
fd = open("/dev/imgproc0", O_RDWR);
```

This is the same thing we did in [Part 3](https://rafae1130.github.io/posts/embedded_linux/embedded-linux-zynq-soc-part-3.html) with `/dev/uio0`.

`open` is also where we can refuse a second user. If the IP can only run one job at a time, the second open just fails with an error (`-EBUSY`).

`release` runs when the file is closed, and also if the application exits without closing it. So the driver always gets a chance to clean up.

### ioctl

After opening the file, we need to control the IP and for that control [`ioctl`](https://docs.kernel.org/driver-api/ioctl.html) used. If you're familiar with AXI lite register programming, this is for that. 
The exact values required for the IP registers are abstracted for the userspace application. We just use the provided macros and the driver will handle the writing of corresponding values to the appropriate registers.

```c
ioctl(fd, IMGPROC_SET_FILTER, BLUR);
ioctl(fd, IMGPROC_START, 0);
```
For example in snippet above, the application never touches a register. It says `BLUR`, and the driver writes whatever value the filter register needs.

`IMGPROC_SET_FILTER` and `IMGPROC_START` are just numbers we define in a header which we as developer provide, and the customer includes that header and uses the macros without knowing the underlying details.

### write/read

`write` is data going to the device. If ioctl was AXI-lite, then read write is AXI-full used for large data transfers.

```c
write(fd, frame, frame_size);
```

The driver copies the frame into a buffer the IP can read from.

`read` is data coming back. The IP writes the data in a buffer that application can read from.
```c
read(fd, out, frame_size);
```


### So what is the difference between ioctl and read/write?

Both move data, so why do we need two ways?

`read` and `write` carry a block of bytes and nothing else. There is nowhere to say what those bytes are for.

`ioctl` carries a command number and a small argument. That is how we say set the filter to `BLUR`.

If we only had `write`, we would have to invent our own rule, such as the first four bytes are the command and the rest is the frame. `ioctl` gives us that already.

![][image4]

**Figure 4: ioctl carries a command. write and read carry the frame. They go to different parts of the IP.**

### poll

`poll` makes the application wait until the driver says something has happened. The interrupt handler is what wakes it up.

```c
struct pollfd pfd = { .fd = fd, .events = POLLIN };

poll(&pfd, 1, -1);          /* sleeps here until the job is done */
read(fd, out, frame_size);
```

This is the same idea as [Part 3](https://rafae1130.github.io/posts/embedded_linux/embedded-linux-zynq-soc-part-3.html), where the application slept inside `read("/dev/uio0")` until the button interrupt arrived. The process uses no CPU while it waits.

# **6\. The platform driver** {#sec-6}

Section 5 was the userspace application side. This is the kernel side.

## 6.1 The skeleton {#sec-6-1}

Here is the whole driver with the function bodies left out, so the shape is visible in one place:

```c
/* defines the compatible string that kernel matches in the device tree */
static const struct of_device_id imgproc_of_match[] = {
    { .compatible = "myco,imgproc-1.0" },
    { }
};

/* which of our functions runs for each userspace call on /dev/imgproc0 as discussed in previous section*/
static const struct file_operations imgproc_fops = {
    .open           = imgproc_open,
    .release        = imgproc_release,
    .unlocked_ioctl = imgproc_ioctl,
    .write          = imgproc_write,
    .read           = imgproc_read,
    .poll           = imgproc_poll,
};

static int imgproc_open(struct inode *inode, struct file *file)
{
    /* give out the fd, refuse a second user. */
}

static int imgproc_release(struct inode *inode, struct file *file)
{
    /* stop the IP and free what open() took */
}

static long imgproc_ioctl(struct file *file, unsigned int cmd, unsigned long arg)
{
    /* configure the IP and start it */
}

static ssize_t imgproc_write(struct file *file, const char *buf, size_t len, loff_t *off)
{
    /* copy the input frame into a buffer the IP can read */
}

static ssize_t imgproc_read(struct file *file, char *buf, size_t len, loff_t *off)
{
    /* copy the result back to the application */
}

static unsigned int imgproc_poll(struct file *file, poll_table *wait)
{
    /* sleep until the interrupt handler says the job is done */
}

static irqreturn_t imgproc_isr(int irq, void *dev_id)
{
    /* clear the interrupt in the IP and wake up poll() */
}

static int imgproc_probe(struct platform_device *pdev)
{
    /* map registers, request the IRQ, create /dev/imgproc0 */
}

static int imgproc_remove(struct platform_device *pdev)
{
    /* free the IRQ, remove /dev/imgproc0 */
}

/* ties the match table to probe and remove */
static struct platform_driver imgproc_driver = {
    .probe  = imgproc_probe,
    .remove = imgproc_remove,
    .driver = {
        .name           = "imgproc",
        .of_match_table = imgproc_of_match,
    },
};

/* registers the driver when the module is loaded */
module_platform_driver(imgproc_driver);
```

**`of_device_id `** defines the compatible string to be compared with the device tree. 

**`imgproc_fops`** tells the kernel which function to run for each userspace function call. For example the in the above platform driver, if the userspace application calls `read()` on `/dev/imgproc0`, the platform driver will run `imgproc_read()`. The skeleton above shows only a few of the available operations. Add link to more  operations here......

**`imgproc_driver`** struct is provided to the kernel. It contains information about struct *`of_device_id `* and the remove and probe function for this driver. Then the kernel can run the probe function if it sees a matching compatible string of *`of_device_id `* in device tree


The rest of this section goes through these in the order they run.

![][image5]

**Figure 5: probe() runs once, when the compatible string matches a device tree node. remove() undoes it when the module is unloaded.**

## 6.2 imgproc_of_match: how Linux finds the driver {#sec-6-2}

The device tree node names the hardware with a `compatible` string. The driver lists the same string in its match table.

Linux compares the two strings. If they are equal, it calls `probe()`.

That is the whole mechanism. No address checking, no reading of the hardware to see what is there. Just a string compare.

![][image6]

**Figure 6: The compatible string is the only connection between the device tree node and the driver.**

### What if it does not match?

Nothing happens, and this is the part that costs people an afternoon.

The module loads without an error. `probe` never runs, `/dev` never appears, and nothing is printed. From the kernel's side nothing went wrong. A driver simply did not match a device.

## 6.3 struct imgproc: what the driver remembers {#sec-6-3}

`probe()` allocates one of these for each IP it finds. Every other function works on it.

```c
struct imgproc {
    void __iomem      *base;   /* the mapped registers */
    int                irq;
    wait_queue_head_t  wq;     /* poll() sleeps here */
    bool               busy;   /* is a job running */
    bool               done;   /* set by the interrupt handler */
};
```

`__iomem` is just a marker. It says this pointer is hardware registers and not normal memory.


## 6.4 imgproc_probe: getting the IP ready {#sec-6-4}

`probe()` runs when the match is found, once for each matching node. Two copies of the IP in the bitstream means two nodes, so `probe` runs twice.

1. allocate the struct above
2. map the register window from the `reg` property, and store it in `base`
3. set up the wait queue that `poll()` will sleep on
4. get the interrupt number from the `interrupts` property and request it
5. create `/dev/imgproc0`

Steps 4 and 5 come last on purpose. After the interrupt is requested the handler can run at any moment, and once `/dev` exists an application can open the device. Everything they touch has to be ready before that.

### Example: from reg to a register write

Take the AXI GPIO from [Part 3](https://rafae1130.github.io/posts/embedded_linux/embedded-linux-zynq-soc-part-3.html), so we can compare the two sides directly.

The application cleared its status register like this:

```c
/* userspace, after mmap */
gpioRegs[GPIO_IPISR] = 1;
```

If we had written a driver for it, the same write looks like this:

```c
/* kernel, after step 2 filled in base */
writel(1, dev->base + IPISR);   /* IPISR is 0x120 */
```

Same register, same offset from the datasheet. Only the way we reach it changed.

![][image7]

**Figure 7: The address in reg becomes a kernel pointer, and the offset lands on the same register the Part 3 application wrote to.**

## 6.5 imgproc_open and imgproc_release {#sec-6-5}

The kernel hands us the `inode` and the `file`, not our struct. `open()` finds the struct from the `/dev` node it was registered with, checks nobody else has the IP, and stores it in `file->private_data` so every later call can find it.

```c
if (dev->busy)
    return -EBUSY;

dev->busy = true;
file->private_data = dev;
```

`release()` is the other end. It stops the IP and clears `busy`, so the next process can open the device.

## 6.6 imgproc_ioctl {#sec-6-6}

Turns a command number into register writes.

```c
case IMGPROC_SET_FILTER:  writel(arg, dev->base + FILTER);
case IMGPROC_START:       writel(1,   dev->base + CTRL);
```

This is where the register map stays hidden. The application sends `BLUR`, and only the driver knows which register that is.

## 6.7 imgproc_write and imgproc_read {#sec-6-7}

`write()` copies the frame from the application into the buffer the IP reads. The kernel cannot use an application pointer directly, so this goes through `copy_from_user`.

`read()` copies the result back the same way, and clears `dev->done`.

## 6.8 imgproc_poll and imgproc_isr {#sec-6-8}

A wait queue is just a place to park a process. `poll()` puts the calling process on `dev->wq`, and the scheduler stops giving it CPU.

If `dev->done` is already set, `poll()` returns straight away instead.

The handler is what wakes it up. It is short on purpose:

```c
writel(1, dev->base + ISR);        /* clear it in the IP */
dev->done = 1;                     /* remember what happened */
wake_up_interruptible(&dev->wq);   /* poll() returns now */
```

The first line matters. If we do not clear the interrupt in the IP, it fires again immediately.

The handler runs in interrupt context, which means it is not inside any process and it cannot sleep. So it wakes the queue and lets the woken process do the real work.

## 6.9 imgproc_remove {#sec-6-9}

`remove()` is `probe` backwards:

1. remove `/dev`, so no new process can open the device
2. make sure the IP is stopped, in case a job was still running
3. free the interrupt

`free_irq()` waits for a handler that is already running to finish, so it has to come before anything that handler touches is freed.

### Why does this matter more on an FPGA?

Because we reload bitstreams while Linux keeps running.

If the old driver is still loaded when the new bitstream is programmed, it holds a mapping to registers that just changed. The interrupt line may now belong to a different IP.

<div class="tip-box" markdown="1">

**Note.** So during bring-up the order is: remove the module, program the new bitstream, apply the overlay, load the module again.

</div>

# **7\. Summary** {#sec-7}

* UIO covers registers and interrupts. DMA, cache coherency and more than one process push us into writing a driver.
* AXI-connected PL IPs cannot be discovered by enumeration, so the Device Tree describes them and Linux creates a platform device for each one.
* The `compatible` string is the only link between the node and the driver. If it is wrong, nothing is printed.
* `probe()` runs once per IP: map registers, request the interrupt, create `/dev`. The interrupt and `/dev` come last on purpose.
* One struct per IP holds `base`, the wait queue and the flags. `open()` puts a pointer to it in `file->private_data` so the other functions can find it.
* `ioctl` configures and starts, `write` and `read` move the frame, `poll` parks the process on the wait queue.
* The handler clears the interrupt in the IP, sets `done`, and wakes the queue.

# **8\. What's Next** {#sec-8}

In the next blog we fill in this skeleton and run it on the board: the device tree node, `probe` and `remove`, the file operations, the interrupt handler, and a small application to test it.

# **9\. References** {#sec-9}

* [Linux Device Drivers, 3rd edition (LDD3)](https://lwn.net/Kernel/LDD3/)
* [Driver implementer's API guide](https://docs.kernel.org/driver-api/index.html)
* [Platform devices and drivers](https://docs.kernel.org/driver-api/driver-model/platform.html)
* [Device tree usage model in drivers](https://docs.kernel.org/devicetree/usage-model.html)
* [DMA API and cache coherency](https://docs.kernel.org/core-api/dma-api.html)
* [UIO how-to (Part 3 background)](https://docs.kernel.org/driver-api/uio-howto.html)
* [Zynq-7000 TRM (PL to PS interrupts)](https://docs.amd.com/r/en-US/ug585-zynq-7000-SoC-TRM)

---

**Series:** [Part 1](https://rafae1130.github.io/posts/embedded_linux/embedded-linux-zynq-soc-part-1.html) · [Part 2: Device Tree](https://rafae1130.github.io/posts/embedded_linux/embedded-linux-zynq-soc-part-2.html) · [Part 3: Device Tree Overlay and UIO](https://rafae1130.github.io/posts/embedded_linux/embedded-linux-zynq-soc-part-3.html) · Part 4


[image1]: images/image1_p4.png

[image2]: images/image2_p4.png

[image3]: images/image3_p4.png

[image4]: images/image4_p4.png

[image5]: images/image5_p4.png

[image6]: images/image6_p4.png

[image7]: images/image7_p4.png
