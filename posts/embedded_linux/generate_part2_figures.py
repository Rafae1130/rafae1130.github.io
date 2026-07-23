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


def draw_arrow_h(draw: ImageDraw.ImageDraw, x1: int, y: int, x2: int, width: int = 2) -> None:
    draw.line([x1, y, x2, y], fill="#111111", width=width)
    draw.polygon([(x2, y), (x2 - 8, y - 4), (x2 - 8, y + 4)], fill="#111111")


def draw_arrow_v(draw: ImageDraw.ImageDraw, x: int, y1: int, y2: int, width: int = 2) -> None:
    draw.line([x, y1, x, y2], fill="#111111", width=width)
    draw.polygon([(x, y2), (x - 4, y2 - 8), (x + 4, y2 - 8)], fill="#111111")


def draw_overall_structure(path: Path) -> None:
    W, H = 980, 520
    img = Image.new("RGB", (W, H), "white")
    draw = ImageDraw.Draw(img)
    title_font = load_font(18)
    label_font = load_font(10)
    code_font = load_font(10, mono=True)
    note_font = load_font(10)
    sub_font = load_font(9)

    title = "Overall device tree structure"
    tw, _ = text_size(draw, title, title_font)
    draw.text(((W - tw) / 2, 12), title, fill="#111", font=title_font)

    lx0, ly0, lw, lh = 20, 42, 400, 460
    draw.rectangle([lx0, ly0, lx0 + lw, ly0 + lh], outline="#dddddd", width=1)
    draw.text((lx0 + 10, ly0 + 8), "Node hierarchy under /", fill="#555", font=note_font)

    box_h = 22
    pad_x = 10

    def node_box(x, y, text, fill="#f5f5f5", font=None):
        font = font or label_font
        tw, th = text_size(draw, text, font)
        w = tw + 2 * pad_x
        draw.rectangle([x, y, x + w, y + box_h], fill=fill, outline="#333", width=1)
        draw.text((x + pad_x, y + (box_h - th) / 2 - 1), text, fill="#111", font=font)
        return x, y, x + w, y + box_h

    def hline(x1, x2, y):
        draw.line([x1, y, x2, y], fill="#333", width=1)

    def vline(x, y1, y2):
        draw.line([x, y1, x, y2], fill="#333", width=1)

    root_x = lx0 + 28
    root = node_box(root_x, ly0 + 34, "/")
    trunk_x = root[0] + pad_x + text_size(draw, "/", label_font)[0] // 2

    entries = [
        ("chosen", []),
        ("aliases", []),
        ("cpus", ["cpu@0", "cpu@1"]),
        ("memory@0", []),
        ("reserved-memory", []),
        ("axi", ["serial@e0000000", "i2c@e0004000", "my_ip@40000000"]),
        ("fpga-region", []),
    ]

    child_x = root_x + 28
    y_cursor = root[3] + 16
    prev_mid = None
    for name, children in entries:
        parent = node_box(child_x, y_cursor, name)
        mid_y = parent[1] + box_h // 2
        if prev_mid is None:
            vline(trunk_x, root[3], mid_y)
        else:
            vline(trunk_x, prev_mid, mid_y)
        hline(trunk_x, child_x, mid_y)
        prev_mid = mid_y

        if children:
            sub_x = child_x + 34
            sub_y = parent[3] + 8
            sub_mids = []
            for child in children:
                sub = node_box(sub_x, sub_y, child, fill="#eef3ff", font=sub_font)
                sub_mids.append(sub[1] + box_h // 2)
                branch_x = child_x + 18
                hline(branch_x, sub_x, sub_mids[-1])
                sub_y = sub[3] + 6
            branch_x = child_x + 18
            vline(branch_x, parent[3], sub_mids[0])
            vline(branch_x, sub_mids[0], sub_mids[-1])
            y_cursor = sub_y + 4
        else:
            y_cursor = parent[3] + 10

    rx0, ry0, rw, rh = 440, 42, 520, 460
    draw.rectangle([rx0, ry0, rx0 + rw, ry0 + rh], outline="#dddddd", width=1)
    draw.text((rx0 + 10, ry0 + 8), "Matching DTS skeleton", fill="#555", font=note_font)

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

    y = ry0 + 34
    for line in skeleton.splitlines():
        draw.text((rx0 + 14, y), line, fill="#222", font=code_font)
        y += 14

    img.save(path)


def draw_arrow_up(draw: ImageDraw.ImageDraw, x: int, y_from: int, y_tip: int, width: int = 2) -> None:
    """Vertical arrow with tip at y_tip (y_tip < y_from)."""
    draw.line([x, y_from, x, y_tip], fill="#111111", width=width)
    draw.polygon([(x, y_tip), (x - 4, y_tip + 8), (x + 4, y_tip + 8)], fill="#111111")


def draw_reg_map(path: Path) -> None:
    """
    Original layout: address bar + base/size + single-line reg.
    Base callout from above; Size callout from below — paths never weave.
    """
    W, H = 800, 340
    img = Image.new("RGB", (W, H), "white")
    draw = ImageDraw.Draw(img)
    title_font = load_font(18)
    label_font = load_font(9)
    code_font = load_font(13, mono=True)
    small_font = load_font(9)

    title = "What reg means in the address map"
    tw, _ = text_size(draw, title, title_font)
    draw.text(((W - tw) / 2, 14), title, fill="#111111", font=title_font)

    val1 = "0xE0000000"
    val2 = "0x1000"
    base_label = f"Base {val1}"
    size_label = f"Size {val2}"

    bar_x, bar_y, bar_w, bar_h = 70, 72, 30, 185
    draw.rectangle([bar_x, bar_y, bar_x + bar_w, bar_y + bar_h], outline="#333333", width=1)

    # Range labels above/below, left-aligned to the bar (full margin on the left)
    top_addr = "0x00000000"
    bot_addr = "0xFFFFFFFF"
    draw.text((bar_x, bar_y - 16), top_addr, fill="#555555", font=small_font)
    draw.text((bar_x, bar_y + bar_h + 4), bot_addr, fill="#555555", font=small_font)
    draw.text((bar_x + bar_w + 10, bar_y - 2), "CPU address space", fill="#555555", font=label_font)

    region_top = bar_y + 58
    region_h = 72
    region_bot = region_top + region_h
    draw.rectangle(
        [bar_x, region_top, bar_x + bar_w, region_bot],
        fill="#d8d8d8",
        outline="#666666",
        width=1,
    )

    bracket_x = bar_x + bar_w + 5
    draw.line([bracket_x, region_top, bracket_x + 5, region_top], fill="#333333", width=1)
    draw.line([bracket_x, region_bot, bracket_x + 5, region_bot], fill="#333333", width=1)
    draw.line([bracket_x + 5, region_top, bracket_x + 5, region_bot], fill="#333333", width=1)

    label_x = bracket_x + 10
    # Base aligned with the top of the gray block; Size mid-bracket
    base_label_y = region_top - 6
    size_label_y = region_top + region_h // 2 - 5
    draw.text((label_x, base_label_y), base_label, fill="#111111", font=label_font)
    draw.text((label_x, size_label_y), size_label, fill="#111111", font=label_font)
    draw.text((label_x, region_bot + 2), "0xE0001000", fill="#777777", font=small_font)

    prefix = "reg = < "
    gap = "  "
    suffix = " >;"
    code = prefix + val1 + gap + val2 + suffix
    cx, cy, cw, ch = 340, 145, 420, 48
    draw.rectangle([cx, cy, cx + cw, cy + ch], fill="#fafafa", outline="#333333", width=1)
    tx, ty = cx + 14, cy + 15
    draw.text((tx, ty), code, fill="#111111", font=code_font)

    val1_x = tx + text_size(draw, prefix, code_font)[0]
    val2_x = val1_x + text_size(draw, val1 + gap, code_font)[0]
    val1_w = text_size(draw, val1, code_font)[0]
    val2_w = text_size(draw, val2, code_font)[0]
    val1_cx = val1_x + val1_w // 2
    val2_cx = val2_x + val2_w // 2

    base_src_y = base_label_y + text_size(draw, base_label, label_font)[1] // 2
    size_src_y = size_label_y + text_size(draw, size_label, label_font)[1] // 2
    base_end_x = label_x + text_size(draw, base_label, label_font)[0] + 4
    size_end_x = label_x + text_size(draw, size_label, label_font)[0] + 4

    # base: stay above the code box, drop down onto first value
    base_lane_y = cy - 14
    tip_down = cy - 2
    draw.line([base_end_x, base_src_y, val1_cx, base_src_y], fill="#111111", width=1)
    draw.line([val1_cx, base_src_y, val1_cx, base_lane_y], fill="#111111", width=1)
    draw_arrow_v(draw, val1_cx, base_lane_y, tip_down)

    # size: stay below the code box, point up at second value
    tip_up = cy + ch + 2
    size_lane_y = tip_up + 24
    stub_x = label_x + text_size(draw, size_label, label_font)[0] + 12
    draw.line([size_end_x, size_src_y, stub_x, size_src_y], fill="#111111", width=1)
    draw.line([stub_x, size_src_y, stub_x, size_lane_y], fill="#111111", width=1)
    draw.line([stub_x, size_lane_y, val2_cx, size_lane_y], fill="#111111", width=1)
    draw_arrow_up(draw, val2_cx, size_lane_y, tip_up)

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
