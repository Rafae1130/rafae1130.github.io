# From FPGA Timing to ASIC STA: Part 1 — Leaving the FPGA Fabric



# **1\. Introduction**

- Frame the series: same timing ideas as the Vivado series, different physical reality.
- Promise: by the end of the series, a Vivado STA reader can read Genus/Tempus reports without starting from zero.
- Scope of Part 1: what changes when the design is no longer mapped to LUTs/FFs/BRAMs/routing fabric.

# **2\. What Vivado Hid From You**

- FPGA: pre-placed hard blocks, fixed routing resources, vendor timing models.
- ASIC: you build the chip from a cell library on a process node.
- Why "it met timing in Vivado" does not transfer to an ASIC tapeout checklist.

# **3\. The ASIC Backend Mental Map**

- RTL → synthesis → (physical) place & route → signoff STA.
- Where Genus and Tempus sit relative to Vivado synth / impl / report_timing.
- Optional figure: FPGA flow vs ASIC flow side by side.

**Figure 1: FPGA implementation flow vs ASIC backend flow**

# **4\. Cells Instead of LUTs**

- Standard cells: combinational, sequential, clock, misc.
- Scan cells (DFT hook) — one sentence; full DFT later if needed.
- Drive strength / VT variants as a first mention (detail in later posts).

# **5\. Libraries Replace Device Timing Data**

- Liberty (.lib): timing, power, area per cell.
- LEF: physical shape/pins (preview only; Part 8).
- PVT corners as library variants — why one .lib is not enough.

# **6\. Constraints Stay Familiar (SDC)**

- Clocks, I/O delays, exceptions still live in SDC.
- What moves from "Vivado-inferred" to "you must declare" in ASIC (generated clocks, some I/O).

# **7\. What This Series Will Cover**

- Short roadmap of Parts 2–8.
- What we will *not* cover yet (full Innovus P&R, DRC/LVS, foundry PDK install).

# **8\. What's Next**

- Part 2: synthesis inputs — RTL, liberty, SDC — and how Genus consumes them.


[image1]: images/image1_p1.png
