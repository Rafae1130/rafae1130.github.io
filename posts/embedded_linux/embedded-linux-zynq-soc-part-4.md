# Embedded Linux (Zynq SoC): Part 4 - Linux Device Drivers

*This is Part 4 of the Embedded Linux ([Zynq SoC](https://www.amd.com/en/products/adaptive-socs-and-fpgas/soc/zynq-7000.html)) series. Read [Part 1](https://rafae1130.github.io/posts/embedded_linux/embedded-linux-zynq-soc-part-1.html), [Part 2: Device Tree](https://rafae1130.github.io/posts/embedded_linux/embedded-linux-zynq-soc-part-2.html) and [Part 3: Device Tree Overlay and UIO](https://rafae1130.github.io/posts/embedded_linux/embedded-linux-zynq-soc-part-3.html) if you haven't already.*

In [Part 3](https://rafae1130.github.io/posts/embedded_linux/embedded-linux-zynq-soc-part-3.html) we used [UIO](https://docs.kernel.org/driver-api/uio-howto.html) and a device tree overlay to reach a custom PL IP from a userspace application. We mapped the registers and detected the interrupts using the UIO driver.

All the code we wrote was in userspace and our application interacted with the UIO driver already provided in the kernel.

UIO is enough when we just want MMIO register access or interrupts detection. In this blog we look at when UIO is not enough, and we build and understand the required basics to start writing our own kernel driver in the next blog.

## Table of contents

1. [When UIO is not enough](#sec-1)
2. [Userspace and kernel space](#sec-2)
3. [Why the vendor writes the driver](#sec-3)
4. [Two views of Linux device drivers](#sec-4)
5. [Userspace application interface](#sec-5)
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

[UIO](https://docs.kernel.org/driver-api/uio-howto.html) provided us MMIO access and interrupt detection. For the example design in [Part 3](https://rafae1130.github.io/posts/embedded_linux/embedded-linux-zynq-soc-part-3.html) that was all we needed.

However, UIO is not enough in the following cases:

* **DMA.** The IP moves data by itself instead of the CPU copying it, so it needs memory and buffer allocation/management, which UIO doesn't provide, and a userspace application doesn't have access to large contiguous memory.
* **Cache coherency.** The CPU might still be holding the data frame in cache while the IP reads DRAM directly and gets stale data. Keeping the two in sync is the kernel's job.
* **More than one process.** If two applications try to access the same IP through UIO, it cannot provide arbitration. If there are going to be multiple userspace applications running at the same time accessing the same IP, a kernel driver is required.

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

![][image1]

**Figure 1: Userspace app interaction with driver to reach the PL IP.**

However, since we're dealing with kernel space memory in the driver, extra care needs to be given as a simple bad pointer can hang the whole kernel.

# **3\. Hardware software stack** {#sec-3}

If we build an image processing IP and sell it, we have to ship software that talks to the IP with it (if it is an SoC system).

But we cannot ship the userspace application, because we do not know what the customer is building. One customer can stream data from a camera and another processes image files from disk. Both require different userspace applications.

So we provide the driver instead. It hides the hardware and provides a simple software interface to talk to it.

The customer can use this to talk to the hardware according to the required use case without knowing details about the hardware itself.
Imagine our driver for the image processing IP is called `imgproc.ko`. And after driver is loaded the IP shows up as `/dev/imgproc0`.
```c
fd = open("/dev/imgproc0", O_RDWR);
ioctl(fd, IMGPROC_SET_FILTER, BLUR);
write(fd, frame, frame_size);
poll(...);
read(fd, out, frame_size);
close(fd);
```
In the above snippet of a userspace application, the user uses our provided macros `IMGPROC_SET_FILTER` and `BLUR` to enable functionality of the IP, and simple commands like `write()` and `read()` to perform data transfers, without any underlying hardware details such as register addresses, what exact value to write for specific addresses, and buffer addresses for data transfers.
We'll discuss the above code in more detail below so don't worry if you don't understand everything fully right now.

# **4\. Two views of Linux device drivers** {#sec-4}

There are two separate questions about any driver. What does it look like to the application, and how did Linux find the hardware?

![][image2]

**Figure 2: Kernel driver types on different basis.**

### Why can PCIe and USB be enumerated?

By enumeration it means that the kernel can find out what is connected to its bus when we connect it. We don't have to provide information in the device tree beforehand. That is because when Linux asks what is connected on the bus, the device answers with its information, i.e. registers and interrupts — the same information that we provide in the device tree for non-enumerable devices.

[AXI](https://www.arm.com/architecture/system-architectures/amba/amba-5) has no enumeration. Therefore, reading an address where no IP is mapped gives you a bus error or a hang, so we have to tell the kernel about these devices manually using the [Device Tree](https://www.devicetree.org/). Linux represents these as a [platform device](https://docs.kernel.org/driver-api/driver-model/platform.html) for each IP it finds there.

# **5\. Userspace application interface** {#sec-5}

The driver creates a file in `/dev`. The application opens that file and uses normal file calls on it such as read and write.

These calls are our interface to the driver, and through the driver, to the IP.

The names of these calls are fixed, but what they do is up to us. We will use our image processing IP as the example.

### open and release

`open` is the first step to talk to the hardware. As we have to open a file before doing any file operations, similarly, since these character devices are represented as a file, we have to open it to begin talking to it.

`open` gives back a file descriptor, and every call after that uses it. That file descriptor is our connection to the driver, and through the driver, to the IP.

```c
fd = open("/dev/imgproc0", O_RDWR);
```

This is the same thing we did in [Part 3](https://rafae1130.github.io/posts/embedded_linux/embedded-linux-zynq-soc-part-3.html) with `/dev/uio0`.

`release` runs when the file is closed, and also if the application exits without closing it. So the driver always gets a chance to clean up.

### ioctl

After opening the file, we need to control the IP, and for that we use [`ioctl`](https://docs.kernel.org/driver-api/ioctl.html). If you're familiar with AXI-Lite register programming, this is for that.
The exact values required for the IP registers are abstracted for the userspace application. We just use the provided macros and the driver will handle the writing of corresponding values to the appropriate registers.

```c
ioctl(fd, IMGPROC_SET_FILTER, BLUR);
ioctl(fd, IMGPROC_START, 0);
```
For example in snippet above, the application never touches a register. It says `BLUR`, and the driver writes whatever value the filter register needs.

`IMGPROC_SET_FILTER` and `IMGPROC_START` are just numbers we define in a header which we as developer provide, and the customer includes that header and uses the macros without knowing the underlying details.

### write/read

`write` is data going to the device. If ioctl was AXI-Lite, then read/write is AXI-Full, used for large data transfers.

```c
write(fd, frame, frame_size);
```

The driver copies the frame into a buffer the IP can read from.

`read` is data coming back. The IP writes the data in a buffer that the application can read from.
```c
read(fd, out, frame_size);
```

### ioctl vs read/write

Both are used for data transfer. But the purpose of their data transfer is different.

`read` and `write` transfer a block of data. It's just a data transfer. Similar to AXI-full.

`ioctl` is used for register configuration. It carries a command number and a small argument. That is how we say set the filter to `BLUR`. This is similar to AXI-lite.

If we only had `write`, we would have to invent our own rule, such as the first four bytes are the command and the rest is the frame. `ioctl` gives us that already.

![][image3]

**Figure 3: ioctl configures the registers inside the IP. write and read copy the frame between userspace and kernel memory, both in DRAM, and the IP reaches the kernel side by DMA.**

### poll

Do not confuse `poll()` with polling. Polling means checking the hardware over and over in a loop, which is what we don't want and why we are using interrupts. The `poll()` function is used for interrupt handling through the kernel.

`poll` makes the application wait until the driver says something has happened. The interrupt handler is what wakes it up.

```c
struct pollfd pfd = { .fd = fd, .events = POLLIN };

poll(&pfd, 1, -1);          /* sleeps here until the job is done */
read(fd, out, frame_size);
```

This is the same idea as [Part 3](https://rafae1130.github.io/posts/embedded_linux/embedded-linux-zynq-soc-part-3.html), where the application slept inside `read("/dev/uio0")` until the button interrupt arrived. The process uses no CPU while it waits.

# **6\. The platform driver** {#sec-6}

Section 5 was the userspace application side. This is the kernel side.

`imgproc.ko` is a **loadable kernel module**. We insert it after boot and we can take it out again. That is different from a driver **built into** the kernel, which is compiled into the kernel image and is there from boot, with no `.ko` and no `rmmod`.

## platform device vs platform driver

Linux creates a `struct platform_device` for every node it finds in the device tree. The kernel stores the device tree node properties, such as the `reg` window and the interrupt, in this struct at boot. Later, when a driver registers with a matching compatible string, the kernel hands it this struct. Our driver doesn't parse the device tree itself. This struct is owned by the kernel and our driver reads it to access the properties defined in the device tree.

## 6.1 The skeleton {#sec-6-1}

Here is the whole driver with the function bodies left out, so the shape is visible in one place. This shows only the structure. We'll learn how to write it fully and compile it in the next blog.

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
    /* makes the communication with device available and give out the fd */
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
    /* report if the job is done; if not, the calling
       userspace application sleeps on wq */
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

/* declares the module's license to the kernel */
MODULE_LICENSE("GPL");
```

**`imgproc_fops`** tells the kernel which function to run for each userspace call. For example, in the platform driver above, if the userspace application calls `read()` on `/dev/imgproc0`, the driver runs `imgproc_read()`. The skeleton shows only a few of the available operations. The full [`file_operations`](https://docs.kernel.org/filesystems/api-summary.html) struct has more (`llseek`, `mmap`, `fsync`, and others); we only fill in the ones our IP needs.

| Userspace call | Driver function |
| --- | --- |
| `open()` | `imgproc_open` |
| `close()` | `imgproc_release` |
| `ioctl()` | `imgproc_ioctl` |
| `write()` | `imgproc_write` |
| `read()` | `imgproc_read` |
| `poll()` | `imgproc_poll` |

**`imgproc_driver`** is the struct we give the kernel. It points at `of_device_id` and at `probe` / `remove`. The kernel runs `probe` if it sees a matching compatible string in the device tree.

**`MODULE_LICENSE`** is not optional. If you leave it out, the kernel treats the module as proprietary and blocks it from using large parts of the kernel API, so a driver like ours will usually fail to load.

The rest of this section goes through these in the order they run.

![][image4]

**Figure 4: Userspace app and driver flow.**

`insmod` and `rmmod` are the commands to load and remove a loadable module. `lsmod` only lists what is already loaded.

## 6.2 imgproc_of_match: how Linux finds the driver {#sec-6-2}

**`of_device_id`** defines the compatible string to compare with the device tree.

![][image5]

**Figure 5: The compatible string match between the device tree node and the driver.**

In [Part 3](https://rafae1130.github.io/posts/embedded_linux/embedded-linux-zynq-soc-part-3.html) we had to tell the UIO driver which string to look for, with `modprobe uio_pdrv_genirq of_id=generic-uio`, because that driver ships without a match table of its own. Our driver does not need that. Its table is compiled into `imgproc.ko`, so the kernel already knows what to match on as soon as the module is loaded.

The rest of the Part 3 flow is unchanged. We'll have to program the bitstream and apply a device tree overlay so Linux knows the IP exists. The only difference is that the overlay node now says `compatible = "myco,imgproc-1.0"` instead of `"generic-uio"`, so the kernel binds our driver to it instead of the UIO one.

## 6.3 struct imgproc: what the driver remembers {#sec-6-3}

This is not fixed and can be different for different drivers depending on the requirement. `probe()` fills it and other functions use it:

```c
struct imgproc {
    void __iomem      *base;   /* the mapped registers */
    int                irq;
    wait_queue_head_t  wq;     /* waiting processes sleep here */
    bool               done;   /* set by the interrupt handler */
};
```

`base` and `irq` come from the platform device struct in `probe()`. `wq` and `done` are driver state.

A wait queue is how the kernel sleeps a process until something happens. A process waiting on this device is placed on `wq`, and the interrupt handler wakes the process waiting there once it has handled the interrupt.

`open()` stores a pointer to this struct in `file->private_data`, so `ioctl`, `read`, `write`, and `poll` can use this struct later.

## 6.4 imgproc_probe: getting the IP ready {#sec-6-4}

`probe()` runs when the match is found, once for each matching node. It performs the following main functions:

1. read `reg` and `interrupts` from the platform device struct in the kernel
2. map the register window into `base`, and store the interrupt number in `irq`
3. request `irq`, so that `imgproc_isr` runs when the IP raises the interrupt
4. create `/dev/imgproc0`

## 6.5 imgproc_open and imgproc_release {#sec-6-5}

When `/dev/imgproc0` is opened in the userspace application like:
```c
int fd = open("/dev/imgproc0", O_RDWR);
```

That call lands in the driver's `imgproc_open` because that is what `open` was mapped to in **`imgproc_fops`**. This is where the driver sets up whatever this session needs before any other call can be made.

Similarly `release()` is mapped to `imgproc_release`. It stops the IP and undoes what `open` set up.

## 6.6 imgproc_ioctl {#sec-6-6}

Allows a readable interface to write MMIO registers from userspace.

In the userspace application:

```c
ioctl(fd, IMGPROC_SET_FILTER, BLUR);
ioctl(fd, IMGPROC_START, 0);
```

In `imgproc_ioctl` inside the device driver:

* `IMGPROC_SET_FILTER` + `BLUR` → `writel(1, dev->base + FILTER)`
* `IMGPROC_SET_FILTER` + `SHARP` → `writel(2, dev->base + FILTER)`
* `IMGPROC_START` → `writel(1, dev->base + CTRL)`

This is where the register map stays hidden. The application sends `BLUR`, and the driver knows which value to write at which register to provide this functionality.

## 6.7 imgproc_write and imgproc_read {#sec-6-7}

`write()` copies the frame from the application into the buffer the IP reads.

The application passes a pointer to the data buffer, but that pointer is a virtual address that only means something inside that one process. So the driver does not use it directly. Instead, `copy_from_user` translates it and copies the data.

`read()` copies the result back the same way, i.e. `copy_to_user`.

## 6.8 imgproc_poll and imgproc_isr {#sec-6-8}

`imgproc_poll` runs and returns straight away. The kernel's poll core is what sleeps/wakes the application, and it is also what calls `imgproc_poll`.

`done` is the flag in `struct imgproc` that `imgproc_isr` sets when the interrupt is triggered by the IP. The `done` flag is just what suits our driver. Other drivers use a counter or a buffer, depending on what the device needs.

1. the application calls `poll()`
2. `poll()` goes into the kernel's poll core
3. the poll core calls `imgproc_poll`
4. `imgproc_poll` gives the poll core `wq` as the queue to wake the application on, then checks `done`
5. `done` is false, so `imgproc_poll` returns "not ready"
6. the poll core sleeps the application on `wq`
7. the PL interrupt fires and `imgproc_isr` runs: it clears the interrupt in the IP, sets `done`, and wakes `wq`
8. the wake lifts the poll core, which calls `imgproc_poll` again
9. `done` is true this time, so `imgproc_poll` returns "ready" and the application's `poll()` returns

![][image6]

**Figure 6: Interrupt handling flow in our example driver.**

If `done` is already true back at step 4, `imgproc_poll` returns "ready" immediately and the application never sleeps.

`imgproc_isr` has no userspace mapping. It never calls `imgproc_poll` by itself. It only sets `done` and wakes `wq`. The poll core detects that wake and calls `imgproc_poll`.

Interrupt management in kernel space still confuses me. So don't worry if you don't understand this in the first read.

### imgproc_isr vs UIO

In [Part 3](https://rafae1130.github.io/posts/embedded_linux/embedded-linux-zynq-soc-part-3.html) the same PL interrupt reached the application, but the work was split differently.

| | UIO (Part 3) | our driver |
| --- | --- | --- |
| the application sleeps in | `read("/dev/uio0")` | `poll()` |
| clears the interrupt in the IP | the application, through the mapped registers | `imgproc_isr` |
| re-arms the interrupt | the application, with `write()` to `/dev/uio0` | nothing to re-arm, the driver never masks it |
| knows what the registers mean | the application | the driver |

`uio_pdrv_genirq` is generic. The overlay gives it the address window through `reg`, but nothing tells it which register in that space is the interrupt status, or what to write to clear it, so it cannot clear the interrupt itself.

All it can do is mask the line and wake the application, which then clears the interrupt through the mapped registers and calls `write()` to re-arm.

While that line is masked, no further interrupt from the IP reaches the kernel. The device stays deaf until the application has been scheduled, has cleared the IP, and has re-armed the line. This is why using UIO for interrupt handling has more latency compared to a kernel driver.

Our `imgproc_isr` in the driver knows the register map because we provide it that information while writing the driver, so it clears the source itself and the line never has to be masked. The next interrupt can arrive while the application is still asleep, and there is nothing to re-arm.

With UIO everything device specific stays in the application, whereas with our own kernel driver it moves into the ISR, and the application only learns that the job is done.

## 6.9 imgproc_remove {#sec-6-9}

`remove()` is the inverse of `probe`:

1. remove `/dev`, so no new process can open the device
2. make sure the IP is stopped, in case a job was still running
3. free the interrupt

`free_irq()` waits for a handler that is already running to finish, so it has to come before anything that handler touches is freed.

### Why does this matter more on an FPGA?

Because we reload bitstreams while Linux keeps running, and if the old driver is still loaded when the new bitstream is programmed, it will hold a mapping to registers that just changed and the interrupt line may now belong to a different IP.

<div class="tip-box" markdown="1">

**Note.** So during bring-up the order is: remove the module, program the new bitstream, apply the overlay, load the module again.

</div>

# **7\. Summary** {#sec-7}

* UIO covers registers and interrupts. DMA, cache coherency and more than one process push us into writing a driver.
* `imgproc.ko` is a loadable module (`insmod` / `rmmod`). A built-in driver is compiled into the kernel and cannot be unloaded.
* AXI-connected PL IPs cannot be discovered by enumeration, so the Device Tree describes them and Linux creates a platform device for each one.
* The `compatible` string is the only link between the node and the driver. If it is wrong, the driver won't work.
* `probe()` runs when the `compatible` string in the driver matches a device tree node. It maps the registers, requests the interrupt, and creates `/dev`.
* `ioctl` configures, `write` and `read` move the frame, `poll` sleeps the process waiting for interrupt.
* The handler clears the interrupt in the IP, and wakes the application.

# **8\. What's Next** {#sec-8}

In the next blog we will create our own driver for a custom acceleration IP and will run it on board.

# **9\. References** {#sec-9}

* [Linux Device Drivers, 3rd edition (LDD3)](https://lwn.net/Kernel/LDD3/)
* [Driver implementer's API guide](https://docs.kernel.org/driver-api/index.html)
* [`file_operations`](https://docs.kernel.org/filesystems/api-summary.html)
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

<!-- post-nav -->
<div class="post-nav">
  <a class="nav-prev" href="https://rafae1130.github.io/posts/embedded_linux/embedded-linux-zynq-soc-part-3.html">&larr; Previous</a>
  <a class="nav-home" href="https://rafae1130.github.io/">Home</a>
</div>
<!-- /post-nav -->
