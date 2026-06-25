import csv
import os
import sys
import time
from ctypes import WinDLL, byref, c_char_p, c_int, create_string_buffer
from datetime import datetime
from pathlib import Path


APP_DIR = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
RESOURCE_DIR = Path(getattr(sys, "_MEIPASS", APP_DIR))
TMCTL_DIR = RESOURCE_DIR / "tmctl8020" / "dll"
OUTPUT_ROOT = APP_DIR / "waveforms"

TM_CTL_USBTMC3 = 12
CHANNELS = [1, 2, 3, 4]

TMCTL_ERRORS = {
    0: "No error",
    1: "Timeout",
    2: "Target device not found",
    4: "Connection with the device failed",
    8: "Not connected to the device",
    16: "Already connected to the device",
    32: "The PC is not compatible",
    64: "Illegal function parameter",
    256: "Send error",
    512: "Receive error",
    1024: "Received data is not block data",
    4096: "System error",
    8192: "Illegal device ID",
    16384: "Unsupported function",
    32768: "Not enough buffer",
    65536: "Library missing",
}


def load_tmctl(tmctl_dir=TMCTL_DIR):
    os.add_dll_directory(str(tmctl_dir))
    return WinDLL(os.path.join(str(tmctl_dir), "tmctl64.dll"))


def last_error(dll, device_id):
    code = dll.TmcGetLastError(c_int(device_id))
    return f"{code} ({TMCTL_ERRORS.get(code, 'unknown')})"


def check(ret, message, dll=None, device_id=None):
    if ret != 0:
        if dll is not None and device_id is not None:
            message = f"{message}; last_error={last_error(dll, device_id)}"
        raise RuntimeError(message)


def setup_call(dll, device_id, name, *args):
    ret = getattr(dll, name)(c_int(device_id), *args)
    print(f"{name} ret={ret}, last_error={last_error(dll, device_id)}", flush=True)
    check(ret, f"{name} failed", dll, device_id)


def send(dll, device_id, command):
    print(f">> {command}", flush=True)
    ret = dll.TmcSend(c_int(device_id), c_char_p(command.encode("ascii")))
    check(ret, f"Send failed: {command}", dll, device_id)


def receive_once_text(dll, device_id, chunk_size=4096):
    buf = create_string_buffer(chunk_size)
    length = c_int()
    ret = dll.TmcReceive(c_int(device_id), byref(buf), c_int(chunk_size), byref(length))
    check(ret, "Receive failed", dll, device_id)
    response = buf.raw[: length.value].decode("ascii", errors="replace").strip()
    preview = response[:160] + ("..." if len(response) > 160 else "")
    print(f"<< {preview}", flush=True)
    return response


def receive_text(dll, device_id, chunk_size=4096):
    parts = []
    while True:
        buf = create_string_buffer(chunk_size)
        length = c_int()
        ret = dll.TmcReceive(c_int(device_id), byref(buf), c_int(chunk_size), byref(length))
        check(ret, "Receive failed", dll, device_id)
        parts.append(buf.raw[: length.value])
        if dll.TmcCheckEnd(c_int(device_id)) == 1:
            break

    response = b"".join(parts).decode("ascii", errors="replace").strip()
    preview = response[:160] + ("..." if len(response) > 160 else "")
    print(f"<< {preview}", flush=True)
    return response


def query(dll, device_id, command):
    send(dll, device_id, command)
    return receive_once_text(dll, device_id)


def query_large(dll, device_id, command, chunk_size):
    send(dll, device_id, command)
    return receive_once_text(dll, device_id, chunk_size=chunk_size)


def create_run_folder(root):
    root.mkdir(parents=True, exist_ok=True)

    base_name = datetime.now().strftime("%y%m%d_%H%M")
    candidate = root / base_name
    if not candidate.exists():
        candidate.mkdir()
        return candidate

    index = 1
    while True:
        candidate = root / f"{base_name}_{index}"
        if not candidate.exists():
            candidate.mkdir()
            return candidate
        index += 1


def search_address(dll):
    print("Searching DLM3024 through USBTMC3...", flush=True)
    buf = create_string_buffer(64 * 127)
    num = c_int()
    ret = dll.TmcSearchDevices(
        c_int(TM_CTL_USBTMC3),
        byref(buf),
        c_int(127),
        byref(num),
        c_char_p(b""),
    )
    check(ret, "No DLM3024 found through USBTMC3")
    if num.value < 1:
        raise RuntimeError("No DLM3024 found. Check USB cable and oscilloscope power.")

    raw = bytes(buf)
    end = raw.find(b"\x00")
    address = raw[:end].decode("ascii")
    print(f"Found address: {address}", flush=True)
    return address


def parse_last_number(response):
    return response.replace(",", " ").split()[-1]


def parse_last_token(response):
    return response.replace(",", " ").split()[-1].strip()


def parse_quoted_string(response):
    start = response.find('"')
    end = response.rfind('"')
    if start >= 0 and end > start:
        return response[start + 1 : end]
    return parse_last_token(response).strip('"')


def unit_for_csv(unit):
    return "".join(ch if ch.isalnum() else "_" for ch in unit).strip("_") or "value"


def parse_waveform_ascii(response):
    if " " in response and response.split()[0].upper().startswith(":WAV"):
        response = response.split(None, 1)[1]
    return [float(item) for item in response.replace("\n", "").split(",") if item.strip()]


def get_channel_settings(dll, device_id, channel):
    vdiv_response = query(dll, device_id, f":CHANNEL{channel}:VDIV?")
    offset_response = query(dll, device_id, f":CHANNEL{channel}:OFFSET?")
    position_response = query(dll, device_id, f":CHANNEL{channel}:POSITION?")
    probe_response = query(dll, device_id, f":CHANNEL{channel}:PROBE:MODE?")
    lscale_mode_response = query(dll, device_id, f":CHANNEL{channel}:LSCALE:MODE?")
    lscale_a_response = query(dll, device_id, f":CHANNEL{channel}:LSCALE:AVALUE?")
    lscale_b_response = query(dll, device_id, f":CHANNEL{channel}:LSCALE:BVALUE?")
    lscale_unit_response = query(dll, device_id, f":CHANNEL{channel}:LSCALE:UNIT?")

    probe_mode = parse_last_token(probe_response)
    lscale_mode = int(float(parse_last_number(lscale_mode_response))) != 0
    lscale_unit = parse_quoted_string(lscale_unit_response)
    raw_unit = "A" if probe_mode.upper().startswith("C") else "V"

    if lscale_mode and lscale_unit:
        display_unit = lscale_unit
        quantity = "scaled"
    elif raw_unit == "A":
        display_unit = "A"
        quantity = "current"
    else:
        display_unit = "V"
        quantity = "voltage"

    raw_vdiv = float(parse_last_number(vdiv_response))
    raw_offset = float(parse_last_number(offset_response))
    position_div = float(parse_last_number(position_response))
    lscale_a = float(parse_last_number(lscale_a_response))
    lscale_b = float(parse_last_number(lscale_b_response))
    display_vdiv = abs(lscale_a) * raw_vdiv if lscale_mode else raw_vdiv
    display_offset = (
        lscale_a * raw_offset + lscale_b
        if lscale_mode
        else raw_offset
    )
    display_zero = lscale_b if lscale_mode else 0.0

    return {
        "vdiv": display_vdiv,
        "offset": display_offset,
        "position_div": position_div,
        "display_zero": display_zero,
        "raw_vdiv": raw_vdiv,
        "raw_offset": raw_offset,
        "probe_mode": probe_mode,
        "lscale_mode": lscale_mode,
        "lscale_a": lscale_a,
        "lscale_b": lscale_b,
        "lscale_unit": lscale_unit,
        "display_unit": display_unit,
        "quantity": quantity,
    }


def save_channel_csv(dll, device_id, output_folder, channel, idn, max_points=None, save_percent=100):
    print(f"Saving CH{channel}...", flush=True)
    send(dll, device_id, f":WAVEFORM:TRACE {channel}")
    send(dll, device_id, ":WAVEFORM:RECORD 0")
    channel_settings = get_channel_settings(dll, device_id, channel)

    length_response = query(dll, device_id, ":WAVEFORM:LENGTH?")
    record_length = int(float(parse_last_number(length_response)))
    percent_points = max(1, int(record_length * save_percent / 100))
    point_count = percent_points if max_points is None else min(max_points, percent_points, record_length)

    sample_rate_response = query(dll, device_id, ":WAVEFORM:SRATE?")
    sample_rate = float(parse_last_number(sample_rate_response))
    trigger_response = query(dll, device_id, ":WAVEFORM:TRIGGER?")
    trigger_point = int(float(parse_last_number(trigger_response)))

    send(dll, device_id, ":WAVEFORM:FORMAT ASCII")
    send(dll, device_id, ":WAVEFORM:START 0")
    send(dll, device_id, f":WAVEFORM:END {point_count - 1}")

    receive_buffer_size = max(1024 * 1024, point_count * 20)
    waveform = query_large(dll, device_id, ":WAVEFORM:SEND?", receive_buffer_size)
    values = parse_waveform_ascii(waveform)
    if channel_settings["lscale_mode"]:
        values = [
            channel_settings["lscale_a"] * value + channel_settings["lscale_b"]
            for value in values
        ]

    csv_path = output_folder / f"CH{channel}.csv"
    value_column = f"{channel_settings['quantity']}_{unit_for_csv(channel_settings['display_unit'])}"
    with csv_path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(["instrument", idn])
        writer.writerow(["channel", f"CH{channel}"])
        writer.writerow(["quantity", channel_settings["quantity"]])
        writer.writerow(["display_unit", channel_settings["display_unit"]])
        writer.writerow(["vertical_scale_per_div", channel_settings["vdiv"]])
        writer.writerow(["vertical_scale_unit", channel_settings["display_unit"]])
        writer.writerow(["vertical_offset", channel_settings["offset"]])
        writer.writerow(["vertical_offset_unit", channel_settings["display_unit"]])
        writer.writerow(["vertical_position_div", channel_settings["position_div"]])
        writer.writerow(["vertical_position_unit", "div"])
        writer.writerow(["display_zero_value", channel_settings["display_zero"]])
        writer.writerow(["raw_vertical_scale_per_div", channel_settings["raw_vdiv"]])
        writer.writerow(["raw_vertical_offset", channel_settings["raw_offset"]])
        writer.writerow(["probe_mode", channel_settings["probe_mode"]])
        writer.writerow(["linear_scale_enabled", int(channel_settings["lscale_mode"])])
        writer.writerow(["linear_scale_A", channel_settings["lscale_a"]])
        writer.writerow(["linear_scale_B", channel_settings["lscale_b"]])
        writer.writerow(["linear_scale_unit", channel_settings["lscale_unit"]])
        writer.writerow(["sample_rate_Hz", sample_rate])
        writer.writerow(["record_length_points", record_length])
        writer.writerow(["save_percent", save_percent])
        writer.writerow(["saved_points", len(values)])
        writer.writerow(["display_duration_s", record_length / sample_rate])
        writer.writerow(["seconds_per_div", record_length / sample_rate / 10])
        writer.writerow(["trigger_point_index", trigger_point])
        writer.writerow([])
        writer.writerow(["index", "time_s", value_column])
        for index, value in enumerate(values):
            time_s = (index - trigger_point) / sample_rate
            writer.writerow([index, time_s, value])

    return csv_path, len(values)


def save_waveforms(tmctl_dir=TMCTL_DIR, output_root=OUTPUT_ROOT, channels=None, max_points=None, save_percent=100):
    channels = CHANNELS if channels is None else channels
    output_root = Path(output_root)
    dll = load_tmctl(tmctl_dir)
    address = search_address(dll)

    device_id = c_int()
    print("Initializing...", flush=True)
    ret = dll.TmcInitialize(c_int(TM_CTL_USBTMC3), c_char_p(address.encode("ascii")), byref(device_id))
    check(ret, "Initialize failed")

    try:
        setup_call(dll, device_id.value, "TmcSetTimeout", c_int(300))
        setup_call(dll, device_id.value, "TmcSetTerm", c_int(2), c_int(1))
        setup_call(dll, device_id.value, "TmcSetRen", c_int(1))
        setup_call(dll, device_id.value, "TmcDeviceClear")
        time.sleep(0.5)

        idn = query(dll, device_id.value, "*IDN?")
        print(idn, flush=True)

        send(dll, device_id.value, "STOP")
        output_folder = create_run_folder(output_root)
        print(f"Output folder: {output_folder}", flush=True)

        for channel in channels:
            csv_path, saved_points = save_channel_csv(
                dll,
                device_id.value,
                output_folder,
                channel,
                idn,
                max_points=max_points,
                save_percent=save_percent,
            )
            print(f"Saved CH{channel}: {saved_points} points -> {csv_path}", flush=True)

        return output_folder
    finally:
        print("Returning oscilloscope to local mode.", flush=True)
        dll.TmcGotoLocal(c_int(device_id.value))
        print("Closing TMCTL session.", flush=True)
        dll.TmcFinish(c_int(device_id.value))


def main():
    save_waveforms()
    return 0


if __name__ == "__main__":
    sys.exit(main())
