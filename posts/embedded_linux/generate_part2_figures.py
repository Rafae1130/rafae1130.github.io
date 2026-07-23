"""Generate Part 2 teaching figures: overall structure, reg map, phandle."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

IMG_DIR = Path(__file__).resolve().parent / "images"


def load_font(size: int, mono: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    if mono:
        candidates = [r"C:\Windows\Fonts\consola.ttf", r"C:\Windows\Fonts\cour.ttf"]
    else:
        candidates = [r"C:\Windows\Fonts\arial.ttf", r"C:\Windows\Fonts\calibri.ttf"]
    for path in candidates:
        p = Path(path)
        if p.exists():
            try:
                return ImageFont.truetype(str(p), size=size)
            except OSError:
                continue
    return ImageFont.load_default()


def text_size(draw: ImageDraw.ImageDraw, text: str, font) -> tuple[int, int]:
    box = draw.textbbox((0, 0), text, font=font)
    return box[2] - box[0], box[3] - box[1]


def draw_arrow(draw: ImageDraw.ImageDraw, points: list[tuple[int, int]], width: int = 2) -> None:
    if len(points) < 2:
        return
    draw.line(points, fill="#111111", width=width)
    x1, y1 = points[-2]
    x2, y2 = points[-1]
    if abs(x2 - x1) >= abs(y2 - y1):
        dx = -10 if x2 > x1 else 10
        draw.polygon([(x2, y2), (x2 - dx, y2 - 4), (x2 - dx, y2 + 4)], fill="#111111")
    else:
        dy = -10 if y2 > y1 else 10
        draw.polygon([(x2, y2), (x2 - 4, y2 - dy), (x2 + 4, y2 - dy)], fill="#111111")


def draw_overall_structure(path: Path) -> None:
    W, H = 920, 820
    img = Image.new("RGB", (W, H), "white")
    draw = ImageDraw.Draw(img)
    title_font = load_font(18)
    label_font = load_font(11)
    code_font = load_font(10, mono=True)
    note_font = load_font(10)

    title = "Overall device tree structure"
    tw, _ = text_size(draw, title, title_font)
    draw.text(((W - tw) / 2, 14), title, fill="#111", font=title_font)

    box_w, box_h, gap = 96, 24, 12

    def node_box(x, y, text, fill="#f5f5f5", width=None, font=None):
        w = width or box_w
        font = font or label_font
        draw.rectangle([x, y, x + w, y + box_h], fill=fill, outline="#333", width=1)
        ttw, tth = text_size(draw, text, font)
        draw.text((x + (w - ttw) / 2, y + (box_h - tth) / 2 - 1), text, fill="#111", font=font)

    def hline(x1, x2, y):
        draw.line([x1, y, x2, y], fill="#333", width=1)

    def vline(x, y1, y2):
        draw.line([x, y1, x, y2], fill="#333", width=1)

    root_x = W // 2 - box_w // 2
    root_y = 44
    node_box(root_x, root_y, "/")
    root_cx = W // 2
    root_bot = root_y + box_h

    tops = ["chosen", "aliases", "cpus", "memory@0", "reserved-memory", "axi", "fpga-region"]
    total = len(tops) * box_w + (len(tops) - 1) * gap
    start_x = (W - total) // 2
    child_y = root_y + 58
    mids = []
    bus_y = root_bot + (child_y - root_bot) // 2
    for i, name in enumerate(tops):
        x = start_x + i * (box_w + gap)
        node_box(x, child_y, name)
        cx = x + box_w // 2
        mids.append(cx)
        vline(cx, bus_y, child_y)
    vline(root_cx, root_bot, bus_y)
    hline(mids[0], mids[-1], bus_y)

    sub_y = child_y + 58
    sub_w = 104
    sub_font = load_font(8)

    cpus_i = tops.index("cpus")
    cpus_cx = start_x + cpus_i * (box_w + gap) + box_w // 2
    cpu_names = ["cpu@0", "cpu@1"]
    cpu_total = len(cpu_names) * sub_w + gap
    cpu_start = cpus_cx - cpu_total // 2
    cpu_bus = child_y + box_h + (sub_y - child_y - box_h) // 2
    for i, name in enumerate(cpu_names):
        x = cpu_start + i * (sub_w + gap)
        node_box(x, sub_y, name, fill="#eef3ff", width=sub_w, font=sub_font)
        cx = x + sub_w // 2
        vline(cx, cpu_bus, sub_y)
    vline(cpus_cx, child_y + box_h, cpu_bus)
    hline(cpu_start + sub_w // 2, cpu_start + sub_w + gap + sub_w // 2, cpu_bus)

    axi_i = tops.index("axi")
    axi_cx = start_x + axi_i * (box_w + gap) + box_w // 2
    axi_children = ["serial@e0000000", "i2c@e0004000", "my_ip@40000000"]
    sub_total = len(axi_children) * sub_w + (len(axi_children) - 1) * 8
    sub_start = axi_cx - sub_total // 2
    axi_bus = cpu_bus
    sub_centers = []
    for i, name in enumerate(axi_children):
        x = sub_start + i * (sub_w + 8)
        node_box(x, sub_y, name, fill="#eef3ff", width=sub_w, font=sub_font)
        cx = x + sub_w // 2
        sub_centers.append(cx)
        vline(cx, axi_bus, sub_y)
    vline(axi_cx, child_y + box_h, axi_bus)
    hline(sub_centers[0], sub_centers[-1], axi_bus)

    draw.text((24, sub_y + 36), "Node hierarchy under /", fill="#555", font=note_font)

    skeleton = """/dts-v1/;

/ {
    model = "Example SoC Board";
    compatible = "vendor,board", "vendor,soc";
    #address-cells = <1>;
    #size-cells = <1>;

    chosen { };
    aliases { };

    cpus {
        cpu@0 { };
        cpu@1 { };
    };

    memory@0 { };
    reserved-memory { };

    axi {
        serial@e0000000 { };
        i2c@e0004000 { };
        my_ip@40000000 { };
    };

    fpga-region { };
};"""

    code_y = sub_y + 62
    rx, ry, rw, rh = 36, code_y, W - 72, 300
    draw.rectangle([rx, ry, rx + rw, ry + rh], fill="#fafafa", outline="#ccc", width=1)
    draw.text((rx + 8, ry - 18), "Matching DTS skeleton", fill="#555", font=note_font)
    y = ry + 10
    for line in skeleton.splitlines():
        draw.text((rx + 12, y), line, fill="#222", font=code_font)
        y += 14

    img.save(path)


def draw_reg_map(path: Path) -> None:
    W, H = 700, 430
    img = Image.new("RGB", (W, H), "white")
    draw = ImageDraw.Draw(img)
    title_font = load_font(18)
    label_font = load_font(12)
    code_font = load_font(13, mono=True)
    small_font = load_font(10)

    title = "What reg means in the address map"
    tw, _ = text_size(draw, title, title_font)
    draw.text(((W - tw) / 2, 14), title, fill="#111", font=title_font)

    bar_x, bar_y, bar_w, bar_h = 62, 62, 34, 250
    draw.rectangle([bar_x, bar_y, bar_x + bar_w, bar_y + bar_h], outline="#333", width=1)
    draw.text((bar_x + bar_w + 10, bar_y - 2), "CPU address space", fill="#444", font=small_font)
    draw.text((bar_x - 6, bar_y - 12), "0x00000000", fill="#666", font=small_font, anchor="rt")
    draw.text((bar_x - 6, bar_y + bar_h + 2), "0xFFFFFFFF", fill="#666", font=small_font, anchor="rt")

    region_top = bar_y + 68
    region_h = 52
    region_bot = region_top + region_h
    draw.rectangle([bar_x, region_top, bar_x + bar_w, region_bot], fill="#d8d8d8", outline="#666", width=1)

    base_label = "BASE 0xE0000000"
    size_label = "SIZE 0x1000"
    draw.text((bar_x + bar_w + 16, region_top - 6), base_label, fill="#111", font=label_font)
    draw.text((bar_x + bar_w + 16, region_bot - 4), "0xE0001000", fill="#666", font=small_font)

    bx = bar_x + bar_w + 8
    draw.line([bx, region_top, bx + 7, region_top], fill="#333", width=1)
    draw.line([bx, region_bot, bx + 7, region_bot], fill="#333", width=1)
    draw.line([bx + 7, region_top, bx + 7, region_bot], fill="#333", width=1)
    size_y = region_top + region_h // 2 - 6
    draw.text((bar_x + bar_w + 20, size_y), size_label, fill="#111", font=label_font)

    code = "reg = < 0xE0000000  0x1000 >;"
    cx, cy, cw, ch = 285, 150, 360, 52
    draw.rectangle([cx, cy, cx + cw, cy + ch], fill="#fafafa", outline="#333", width=1)
    draw.text((cx + 16, cy + 16), code, fill="#111", font=code_font)

    val1_x = cx + 16 + text_size(draw, "reg = < ", code_font)[0]
    val2_x = cx + 16 + text_size(draw, "reg = < 0xE0000000  ", code_font)[0]
    val_y = cy + 18

    base_lx = bar_x + bar_w + 16 + text_size(draw, base_label, label_font)[0]
    base_ly = region_top + 2
    draw_arrow(draw, [(base_lx + 4, base_ly), (val1_x, base_ly), (val1_x, val_y + 12)])

    size_lx = bar_x + bar_w + 20 + text_size(draw, size_label, label_font)[0]
    size_ly = size_y + 8
    route_y = region_bot + 28
    draw_arrow(draw, [(size_lx + 4, size_ly), (val2_x, size_ly), (val2_x, route_y), (val2_x, val_y + 12)])

    img.save(path)


def draw_node_box(
    draw: ImageDraw.ImageDraw,
    x: int,
    y: int,
    title: str,
    lines: list[str],
    font,
    title_font,
    min_w: int = 300,
) -> tuple[int, int, int, int]:
    pad_x, pad_y = 14, 12
    line_h = 16
    inner_w = max(min_w, max(text_size(draw, ln, font)[0] for ln in lines) + 8)
    inner_w = max(inner_w, text_size(draw, title, title_font)[0] + 8)
    h = pad_y + line_h + 8 + len(lines) * line_h + pad_y
    draw.rectangle([x, y, x + inner_w + 2 * pad_x, y + h], fill="#f7f7f7", outline="#333", width=1)
    draw.text((x + pad_x, y + pad_y), title, fill="#111", font=title_font)
    ty = y + pad_y + line_h + 6
    for ln in lines:
        draw.text((x + pad_x, ty), ln, fill="#222", font=font)
        ty += line_h
    return x, y, x + inner_w + 2 * pad_x, y + h


def draw_phandle(path: Path) -> None:
    W, H = 860, 360
    img = Image.new("RGB", (W, H), "white")
    draw = ImageDraw.Draw(img)
    title_font = load_font(18)
    node_title = load_font(12)
    code_font = load_font(11, mono=True)
    note_font = load_font(11)

    title = "Phandle links nodes"
    tw, _ = text_size(draw, title, title_font)
    draw.text(((W - tw) / 2, 14), title, fill="#111", font=title_font)

    serial_lines = [
        "serial@e0000000 {",
        '    compatible = "xlnx,xuartps", "cdns,uart-r1p8";',
        "    reg = <0xe0000000 0x1000>;",
        "    clocks = <&clkc 23>, <&clkc 40>;",
        '    clock-names = "uart_clk", "pclk";',
        "};",
    ]
    clk_lines = [
        "clkc: clock-controller@f8000000 {",
        '    compatible = "xlnx,clkc";',
        "    reg = <0xf8000000 0x1000>;",
        "    #clock-cells = <1>;",
        "};",
    ]

    left = draw_node_box(draw, 36, 58, "UART node", serial_lines, code_font, node_title, min_w=330)
    right = draw_node_box(draw, 470, 58, "Clock controller node", clk_lines, code_font, node_title, min_w=320)

    # Arrow from clocks property in UART node to clkc label on clock-controller node
    clocks_y = 58 + 12 + 16 + 6 + 3 * 16 + 8
    target_x = right[0]
    target_y = 58 + 12 + 16 + 6 + 8
    draw_arrow(
        draw,
        [
            (left[2] - 12, clocks_y + 6),
            (target_x - 24, clocks_y + 6),
            (target_x - 24, target_y + 6),
            (target_x - 4, target_y + 6),
        ],
        width=2,
    )

    draw.text(
        ((W - text_size(draw, "&clkc points at the labeled clock-controller node", note_font)[0]) / 2, 300),
        "&clkc points at the labeled clock-controller node",
        fill="#444",
        font=note_font,
    )

    img.save(path)


def main() -> None:
    IMG_DIR.mkdir(parents=True, exist_ok=True)
    draw_overall_structure(IMG_DIR / "image2_p2.png")
    draw_reg_map(IMG_DIR / "image3_p2.png")
    draw_phandle(IMG_DIR / "image4_p2.png")
    print("Wrote figures to", IMG_DIR)


if __name__ == "__main__":
    main()
