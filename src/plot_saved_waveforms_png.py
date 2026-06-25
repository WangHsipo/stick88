import csv
import json
import math
import struct
import sys
import zlib
from pathlib import Path


APP_DIR = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
OUTPUT_ROOT = APP_DIR / "waveforms"
MAX_BINS_PER_CHANNEL = 900
PLOT_WIDTH = 800
PLOT_HEIGHT = 486
TOP = 72
LEFT = 90
RIGHT = 90
BOTTOM = 42
VERTICAL_DIVS = 8
HORIZONTAL_DIVS = 10

CHANNEL_COLORS = {
    1: (220, 190, 70),
    2: (0, 150, 70),
    3: (255, 0, 190),
    4: (0, 190, 255),
}


FONT = {
    " ": ["000", "000", "000", "000", "000", "000", "000"],
    ".": ["0", "0", "0", "0", "0", "0", "1"],
    "+": ["000", "010", "010", "111", "010", "010", "000"],
    "-": ["000", "000", "000", "111", "000", "000", "000"],
    "/": ["001", "001", "010", "010", "100", "100", "000"],
    "=": ["000", "111", "000", "111", "000", "000", "000"],
    "%": ["1001", "0001", "0010", "0100", "1000", "1001", "0000"],
    "0": ["111", "101", "101", "101", "101", "101", "111"],
    "1": ["010", "110", "010", "010", "010", "010", "111"],
    "2": ["111", "001", "001", "111", "100", "100", "111"],
    "3": ["111", "001", "001", "111", "001", "001", "111"],
    "4": ["101", "101", "101", "111", "001", "001", "001"],
    "5": ["111", "100", "100", "111", "001", "001", "111"],
    "6": ["111", "100", "100", "111", "101", "101", "111"],
    "7": ["111", "001", "001", "010", "010", "100", "100"],
    "8": ["111", "101", "101", "111", "101", "101", "111"],
    "9": ["111", "101", "101", "111", "001", "001", "111"],
    "A": ["010", "101", "101", "111", "101", "101", "101"],
    "C": ["111", "100", "100", "100", "100", "100", "111"],
    "D": ["110", "101", "101", "101", "101", "101", "110"],
    "E": ["111", "100", "100", "110", "100", "100", "111"],
    "F": ["111", "100", "100", "110", "100", "100", "100"],
    "H": ["101", "101", "101", "111", "101", "101", "101"],
    "I": ["111", "010", "010", "010", "010", "010", "111"],
    "M": ["10001", "11011", "10101", "10101", "10001", "10001", "10001"],
    "O": ["111", "101", "101", "101", "101", "101", "111"],
    "P": ["110", "101", "101", "110", "100", "100", "100"],
    "S": ["111", "100", "100", "111", "001", "001", "111"],
    "T": ["111", "010", "010", "010", "010", "010", "010"],
    "U": ["101", "101", "101", "101", "101", "101", "111"],
    "V": ["101", "101", "101", "101", "101", "101", "010"],
}


def latest_waveform_folder():
    folders = [path for path in OUTPUT_ROOT.iterdir() if path.is_dir()]
    if not folders:
        raise RuntimeError(f"No waveform folders found in {OUTPUT_ROOT}")
    return max(folders, key=lambda path: path.stat().st_mtime)


def saved_channels(folder):
    channels = []
    for csv_path in Path(folder).glob("CH*.csv"):
        try:
            channels.append(int(csv_path.stem[2:]))
        except ValueError:
            continue
    return sorted(channels)


def read_metadata(csv_path):
    metadata = {}
    value_column = "value"
    value_index = 2
    with csv_path.open("r", newline="", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        for row in reader:
            if not row:
                continue
            if row[0] == "index":
                requested_column = metadata.get("plot_value_column", "")
                if requested_column and requested_column in row:
                    value_index = row.index(requested_column)
                else:
                    value_index = 2
                value_column = row[value_index]
                break
            if len(row) >= 2:
                metadata[row[0]] = row[1]
    return metadata, value_column, value_index


def waveform_envelope(csv_path, max_bins=MAX_BINS_PER_CHANNEL):
    metadata, value_column, value_index = read_metadata(csv_path)
    saved_points = int(float(metadata.get("saved_points", "0") or "0"))
    bins = max(1, min(max_bins, saved_points or max_bins))
    y_min = [math.inf] * bins
    y_max = [-math.inf] * bins
    y_global_min = math.inf
    y_global_max = -math.inf
    data_started = False
    row_index = 0

    with csv_path.open("r", newline="", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        for row in reader:
            if not row:
                continue
            if row[0] == "index":
                data_started = True
                continue
            if not data_started:
                continue
            if len(row) <= value_index:
                continue
            value = float(row[value_index])
            bin_index = min(bins - 1, int(row_index * bins / max(1, saved_points)))
            y_min[bin_index] = min(y_min[bin_index], value)
            y_max[bin_index] = max(y_max[bin_index], value)
            y_global_min = min(y_global_min, value)
            y_global_max = max(y_global_max, value)
            row_index += 1

    if not math.isfinite(y_global_min) or not math.isfinite(y_global_max):
        y_global_min, y_global_max = -1.0, 1.0
    if y_global_min == y_global_max:
        y_global_min -= 1.0
        y_global_max += 1.0

    return metadata, value_column, y_min, y_max, y_global_min, y_global_max


def new_image(width, height, color=(255, 255, 255)):
    return bytearray(color * width * height)


def set_pixel(img, width, height, x, y, color):
    if 0 <= x < width and 0 <= y < height:
        index = (y * width + x) * 3
        img[index : index + 3] = bytes(color)


def draw_line(img, width, height, x0, y0, x1, y1, color):
    dx = abs(x1 - x0)
    dy = -abs(y1 - y0)
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    err = dx + dy
    while True:
        set_pixel(img, width, height, x0, y0, color)
        if x0 == x1 and y0 == y1:
            break
        e2 = 2 * err
        if e2 >= dy:
            err += dy
            x0 += sx
        if e2 <= dx:
            err += dx
            y0 += sy


def draw_rect(img, width, height, x0, y0, x1, y1, color):
    draw_line(img, width, height, x0, y0, x1, y0, color)
    draw_line(img, width, height, x1, y0, x1, y1, color)
    draw_line(img, width, height, x1, y1, x0, y1, color)
    draw_line(img, width, height, x0, y1, x0, y0, color)


def draw_text(img, width, height, x, y, text, color=(35, 35, 35), scale=2):
    cursor = x
    for char in text.upper():
        glyph = FONT.get(char, FONT[" "])
        for row_index, row in enumerate(glyph):
            for col_index, bit in enumerate(row):
                if bit == "1":
                    for yy in range(scale):
                        for xx in range(scale):
                            set_pixel(img, width, height, cursor + col_index * scale + xx, y + row_index * scale + yy, color)
        cursor += (len(glyph[0]) + 1) * scale


def write_png(path, width, height, pixels, text_overlays=None):
    if text_overlays:
        try:
            from PIL import Image, ImageDraw, ImageFont

            image = Image.frombytes("RGB", (width, height), bytes(pixels))
            draw = ImageDraw.Draw(image)
            chinese_font_path = Path("C:/Windows/Fonts/simfang.ttf")
            english_font_path = Path("C:/Windows/Fonts/times.ttf")
            fallback_font_path = Path("C:/Windows/Fonts/arial.ttf")

            def load_font(kind, size):
                preferred = chinese_font_path if kind == "cn" else english_font_path
                font_path = preferred if preferred.exists() else fallback_font_path
                return ImageFont.truetype(str(font_path), size) if font_path.exists() else ImageFont.load_default()

            def is_cjk(char):
                return "\u3400" <= char <= "\u9fff"

            def render_mixed_text(text, color, font_size):
                fonts = {
                    "cn": load_font("cn", font_size),
                    "en": load_font("en", font_size),
                }
                widths = [
                    max(1, int(math.ceil(draw.textlength(char, font=fonts["cn" if is_cjk(char) else "en"]))))
                    for char in text
                ]
                metrics = [font.getmetrics() for font in fonts.values()]
                max_ascent = max(ascent for ascent, _descent in metrics)
                max_descent = max(descent for _ascent, descent in metrics)
                baseline_y = 4 + max_ascent
                text_image = Image.new(
                    "RGBA",
                    (max(1, sum(widths) + 8), max(1, max_ascent + max_descent + 8)),
                    (255, 255, 255, 0),
                )
                text_draw = ImageDraw.Draw(text_image)
                cursor = 4
                for char, char_width in zip(text, widths):
                    font = fonts["cn" if is_cjk(char) else "en"]
                    text_draw.text((cursor, baseline_y), char, fill=(*color, 255), font=font, anchor="ls")
                    cursor += char_width
                bbox = text_image.getbbox()
                return text_image.crop(bbox) if bbox else text_image

            for overlay in text_overlays:
                x, y, text, color = overlay[:4]
                anchor = overlay[4] if len(overlay) >= 5 else None
                angle = overlay[5] if len(overlay) >= 6 else 0
                font_size = overlay[6] if len(overlay) >= 7 else 14
                font_kind = overlay[7] if len(overlay) >= 8 else "en"
                rotation_side = overlay[8] if len(overlay) >= 9 else None
                font = load_font(font_kind, font_size)
                if angle:
                    bbox = draw.textbbox((0, 0), text, font=font)
                    text_width = bbox[2] - bbox[0] + 8
                    text_height = bbox[3] - bbox[1] + 8
                    text_image = Image.new("RGBA", (text_width, text_height), (255, 255, 255, 0))
                    text_draw = ImageDraw.Draw(text_image)
                    text_draw.text((4 - bbox[0], 4 - bbox[1]), text, fill=(*color, 255), font=font)
                    rotated = text_image.rotate(angle, expand=True, resample=Image.Resampling.BICUBIC)
                    if rotation_side == "left":
                        paste_x = int(round(x - 5 - rotated.width))
                    elif rotation_side == "right":
                        paste_x = int(round(x + 5))
                    else:
                        paste_x = int(round(x - rotated.width / 2))
                    paste_y = int(round(y - rotated.height / 2))
                    image.paste(rotated, (paste_x, paste_y), rotated)
                else:
                    text_image = render_mixed_text(text, color, font_size)
                    paste_x = x
                    paste_y = y
                    if anchor and "m" in anchor:
                        paste_x -= text_image.width / 2
                    elif anchor and "r" in anchor:
                        paste_x -= text_image.width
                    if anchor and "b" in anchor:
                        paste_y -= text_image.height
                    elif anchor and "m" in anchor:
                        paste_y -= text_image.height / 2
                    image.paste(text_image, (int(round(paste_x)), int(round(paste_y))), text_image)
            image.save(path, format="PNG", optimize=True)
            return
        except Exception:
            pass

    raw = bytearray()
    stride = width * 3
    for y in range(height):
        raw.append(0)
        raw.extend(pixels[y * stride : (y + 1) * stride])

    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    png = bytearray(b"\x89PNG\r\n\x1a\n")
    png.extend(chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)))
    png.extend(chunk(b"IDAT", zlib.compress(bytes(raw), level=9)))
    png.extend(chunk(b"IEND", b""))
    Path(path).write_bytes(png)


def format_number(value):
    return f"{value:.6g}"


def channel_plot_info(channel, csv_path):
    metadata, value_column, y_min, y_max, data_ymin, data_ymax = waveform_envelope(csv_path)
    unit = metadata.get("display_unit", value_column.split("_")[-1])
    scale_text = metadata.get("vertical_scale_per_div", "")
    position_text = metadata.get("vertical_position_div")
    display_zero_text = metadata.get("display_zero_value", "0")
    offset_text = metadata.get("vertical_offset")
    try:
        display_ticks = [
            float(value)
            for value in json.loads(metadata.get("protocol_display_ticks", "[]"))
        ][:5]
    except (TypeError, ValueError, json.JSONDecodeError):
        display_ticks = []
    try:
        scale_per_div = abs(float(scale_text))
    except (TypeError, ValueError):
        scale_per_div = 0.0
    try:
        offset = float(offset_text)
    except (TypeError, ValueError):
        offset = None
    try:
        position_div = float(position_text)
    except (TypeError, ValueError):
        position_div = None
    try:
        display_zero = float(display_zero_text)
    except (TypeError, ValueError):
        display_zero = 0.0

    if scale_per_div <= 0:
        scale_per_div = max((data_ymax - data_ymin) / VERTICAL_DIVS, 1e-12)
    if position_div is not None:
        reference_value = display_zero
        position_source = "POSITION"
    else:
        position_div = 0.0
        if offset is None:
            reference_value = (data_ymin + data_ymax) / 2
            position_source = "AUTO"
        else:
            reference_value = offset
            position_source = "OFFSET"

    return {
        "channel": channel,
        "metadata": metadata,
        "unit": unit,
        "scale_per_div": scale_per_div,
        "offset": offset,
        "position_div": position_div,
        "reference_value": reference_value,
        "position_source": position_source,
        "display_ticks": display_ticks,
        "y_min": y_min,
        "y_max": y_max,
    }


def draw_scope_grid(img, image_width, image_height):
    plot_x0 = LEFT
    plot_y0 = TOP
    plot_x1 = PLOT_WIDTH - RIGHT
    plot_y1 = TOP + PLOT_HEIGHT
    plot_w = plot_x1 - plot_x0
    plot_h = plot_y1 - plot_y0

    grid = (220, 224, 228)
    center_grid = (170, 176, 182)
    axis = (90, 96, 102)
    for i in range(1, HORIZONTAL_DIVS):
        x = plot_x0 + i * plot_w // HORIZONTAL_DIVS
        draw_line(img, image_width, image_height, x, plot_y0, x, plot_y1, grid)
    for i in range(1, VERTICAL_DIVS):
        y = plot_y0 + i * plot_h // VERTICAL_DIVS
        draw_line(img, image_width, image_height, plot_x0, y, plot_x1, y, grid)
    draw_line(img, image_width, image_height, plot_x0 + plot_w // 2, plot_y0, plot_x0 + plot_w // 2, plot_y1, center_grid)
    draw_line(img, image_width, image_height, plot_x0, plot_y0 + plot_h // 2, plot_x1, plot_y0 + plot_h // 2, center_grid)
    draw_rect(img, image_width, image_height, plot_x0, plot_y0, plot_x1, plot_y1, axis)
    return plot_x0, plot_y0, plot_x1, plot_y1


def draw_channel_trace(img, image_width, image_height, plot_box, info):
    plot_x0, plot_y0, plot_x1, plot_y1 = plot_box
    plot_w = plot_x1 - plot_x0
    plot_h = plot_y1 - plot_y0
    pixels_per_div = plot_h / VERTICAL_DIVS
    scale_per_div = info["scale_per_div"]
    position_div = info["position_div"]
    reference_value = info["reference_value"]
    trace = CHANNEL_COLORS.get(info["channel"], (230, 230, 230))

    previous_x = None
    previous_y = None
    bins = len(info["y_min"])
    for i, (lo, hi) in enumerate(zip(info["y_min"], info["y_max"])):
        if not math.isfinite(lo) or not math.isfinite(hi):
            continue
        x = int(plot_x0 + i * plot_w / max(1, bins - 1))
        y_lo = max(plot_y0, min(plot_y1, value_to_pixel(info, plot_box, lo)))
        y_hi = max(plot_y0, min(plot_y1, value_to_pixel(info, plot_box, hi)))
        draw_line(img, image_width, image_height, x, y_lo, x, y_hi, trace)
        mid_y = (y_lo + y_hi) // 2
        if previous_x is not None:
            draw_line(img, image_width, image_height, previous_x, previous_y, x, mid_y, trace)
        previous_x, previous_y = x, mid_y


def value_to_pixel(info, plot_box, value):
    _plot_x0, plot_y0, _plot_x1, plot_y1 = plot_box
    plot_h = plot_y1 - plot_y0
    pixels_per_div = plot_h / VERTICAL_DIVS
    value_div = (value - info["reference_value"]) / info["scale_per_div"]
    return int(round(plot_y0 + plot_h / 2 - (value_div + info["position_div"]) * pixels_per_div))


def draw_channel_scale(img, image_width, image_height, plot_box, info):
    ticks = info["display_ticks"]
    if not ticks:
        return []

    plot_x0, plot_y0, plot_x1, plot_y1 = plot_box
    channel = info["channel"]
    color = CHANNEL_COLORS.get(channel, (80, 80, 80))
    axis_positions = {
        1: plot_x0 - 40,
        2: plot_x0 - 5,
        3: plot_x1 + 5,
        4: plot_x1 + 40,
    }
    axis_x = axis_positions[channel]
    is_left = channel in (1, 2)
    text_angle = 90 if is_left else -90
    draw_line(img, image_width, image_height, axis_x, plot_y0, axis_x, plot_y1, color)

    overlays = []
    for value in ticks:
        y = value_to_pixel(info, plot_box, value)
        if y < plot_y0 or y > plot_y1:
            continue
        if is_left:
            draw_line(img, image_width, image_height, axis_x, y, axis_x + 8, y, color)
        else:
            draw_line(img, image_width, image_height, axis_x - 8, y, axis_x, y, color)
        label_y = max(plot_y0 + 8, min(plot_y1 - 8, y))
        rotation_side = "left" if is_left else "right"
        overlays.append((axis_x, label_y, format_number(value), color, "mm", text_angle, 20, "en", rotation_side))
    return overlays


def plot_folder(folder):
    folder = Path(folder).resolve()
    channels = saved_channels(folder)
    if not channels:
        raise RuntimeError(f"No CH*.csv files found in {folder}")

    width = PLOT_WIDTH
    height = TOP + PLOT_HEIGHT + BOTTOM
    image = new_image(width, height)
    plot_box = draw_scope_grid(image, width, height)
    infos = [
        channel_plot_info(channel, folder / f"CH{channel}.csv")
        for channel in channels
    ]
    for info in infos:
        draw_channel_trace(image, width, height, plot_box, info)

    text_overlays = []
    for info in infos:
        text_overlays.extend(draw_channel_scale(image, width, height, plot_box, info))

    info_by_channel = {info["channel"]: info for info in infos}
    plot_x0, plot_y0, plot_x1, plot_y1 = plot_box
    legend_slot_width = (plot_x1 - plot_x0) / 4
    for channel in range(1, 5):
        info = info_by_channel.get(channel)
        if info is None:
            continue
        channel = info["channel"]
        color = CHANNEL_COLORS.get(channel, (230, 230, 230))
        label = f"CH{channel} {format_number(info['scale_per_div'])}{info['unit']}/DIV"
        x = plot_x0 + (channel - 1) * legend_slot_width
        text_overlays.append((x, plot_y1 + 5, label, color, None, 0, 20, "en"))

    protocol_names = {
        info["metadata"].get("protocol_name", "")
        for info in infos
        if info["metadata"].get("protocol_name", "")
    }
    if len(protocol_names) == 1:
        protocol_name = next(iter(protocol_names))
        text_overlays.append(((plot_x0 + plot_x1) / 2, plot_y0 - 5, protocol_name, (0, 0, 0), "mb", 0, 20, "cn"))

    png_path = folder / f"{folder.name}.png"
    write_png(png_path, width, height, image, text_overlays=text_overlays)
    return png_path


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    folder = Path(argv[0]) if argv else latest_waveform_folder()
    png_path = plot_folder(folder)
    print(f"Saved plot: {png_path}", flush=True)
    print(f"PNG size: {png_path.stat().st_size / 1024:.1f} KB", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
