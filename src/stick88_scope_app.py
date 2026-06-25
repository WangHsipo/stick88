import contextlib
import copy
import json
import os
import queue
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk


APP_DIR = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
DEFAULT_OUTPUT_ROOT = APP_DIR / "waveforms"
OLD_NOTE_PATH = APP_DIR / "stick88_note.md"
OLD_README_PATH = APP_DIR / "README.md"
SETTINGS_PATH = APP_DIR / "stick88_settings.json"
APP_VERSION = "1.1.3"

from plot_saved_waveforms_png import plot_folder
from protocol_utils import (
    DEFAULT_PROTOCOLS,
    NO_PROTOCOL,
    find_protocol,
    normalize_protocol,
    normalize_protocols,
    protocols_for_storage,
)
from save_dlm3024_waveform_csv import save_waveforms
from waveform_config import load_config


class QueueWriter:
    def __init__(self, target_queue):
        self.target_queue = target_queue

    def write(self, text):
        if text:
            self.target_queue.put(("log", text))

    def flush(self):
        pass


class ProtocolManagerDialog(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.parent = parent
        self.title("协议管理")
        self.geometry("1120x450")
        self.minsize(1040, 410)
        self.transient(parent)
        self.grab_set()
        self.original_name = None

        self.protocol_name_var = tk.StringVar()
        self.channel_fields = {}
        self._build_ui()
        self._refresh_list()
        if parent.selected_protocol_var.get() != NO_PROTOCOL:
            self._select_protocol(parent.selected_protocol_var.get())

    def _build_ui(self):
        root = ttk.Frame(self, padding=10)
        root.pack(fill="both", expand=True)
        root.columnconfigure(1, weight=1)
        root.rowconfigure(0, weight=1)

        left = ttk.Frame(root)
        left.grid(row=0, column=0, sticky="ns", padx=(0, 10))
        ttk.Label(left, text="已有协议").pack(anchor="w")
        self.protocol_list = tk.Listbox(left, width=20, exportselection=False)
        self.protocol_list.pack(fill="y", expand=True, pady=(5, 0))
        self.protocol_list.bind("<<ListboxSelect>>", self._on_select)

        editor = ttk.LabelFrame(root, text="协议内容", padding=10)
        editor.grid(row=0, column=1, sticky="nsew")
        editor.columnconfigure(2, weight=1)

        ttk.Label(editor, text="协议名称").grid(row=0, column=0, sticky="w", pady=(0, 8))
        ttk.Entry(editor, textvariable=self.protocol_name_var, width=24).grid(
            row=0, column=1, columnspan=5, sticky="w", pady=(0, 8)
        )

        headers = ["启用", "通道", "数据名称", "换算系数", "偏置", "单位", "显示刻度（最多5个）"]
        for column, text in enumerate(headers):
            ttk.Label(editor, text=text).grid(row=1, column=column, sticky="w", padx=(0, 8))

        for channel in range(1, 5):
            fields = {
                "enabled": tk.BooleanVar(value=False),
                "data_name": tk.StringVar(),
                "gain": tk.StringVar(value="1"),
                "bias": tk.StringVar(value="0"),
                "unit": tk.StringVar(),
                "display_ticks": tk.StringVar(value="[]"),
            }
            self.channel_fields[channel] = fields
            row = channel + 1
            ttk.Checkbutton(editor, variable=fields["enabled"]).grid(row=row, column=0, sticky="w")
            ttk.Label(editor, text=f"CH{channel}").grid(row=row, column=1, sticky="w", padx=(0, 8), pady=5)
            ttk.Entry(editor, textvariable=fields["data_name"], width=18).grid(row=row, column=2, sticky="ew", padx=(0, 8))
            ttk.Entry(editor, textvariable=fields["gain"], width=18).grid(row=row, column=3, sticky="ew", padx=(0, 8))
            ttk.Entry(editor, textvariable=fields["bias"], width=14).grid(row=row, column=4, sticky="ew", padx=(0, 8))
            ttk.Entry(editor, textvariable=fields["unit"], width=10).grid(row=row, column=5, sticky="ew")
            ttk.Entry(editor, textvariable=fields["display_ticks"], width=22).grid(
                row=row, column=6, sticky="ew", padx=(8, 0)
            )

        formula = "换算公式：物理量 = (通道数值 - 偏置) × 换算系数；系数和偏置支持 + - * / // % ** 与括号。"
        ttk.Label(editor, text=formula, foreground="#555555", wraplength=650).grid(
            row=6, column=0, columnspan=7, sticky="w", pady=(12, 0)
        )
        ttk.Label(
            editor,
            text="协议名称、数据名称和单位最多 15 个字符；显示刻度使用数组，例如 [-10, 10, 0]。",
            foreground="#555555",
        ).grid(
            row=7, column=0, columnspan=7, sticky="w", pady=(4, 0)
        )

        buttons = ttk.Frame(root)
        buttons.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        ttk.Button(buttons, text="新增", command=self._new_protocol).pack(side="left")
        ttk.Button(buttons, text="保存更改", command=self._save_protocol).pack(side="left", padx=8)
        ttk.Button(buttons, text="删除", command=self._delete_protocol).pack(side="left")
        ttk.Button(buttons, text="关闭", command=self.destroy).pack(side="right")

    def _refresh_list(self):
        self.protocol_list.delete(0, "end")
        for protocol in self.parent.protocols:
            self.protocol_list.insert("end", protocol["name"])

    def _select_protocol(self, name):
        names = [protocol["name"] for protocol in self.parent.protocols]
        if name not in names:
            return
        index = names.index(name)
        self.protocol_list.selection_clear(0, "end")
        self.protocol_list.selection_set(index)
        self.protocol_list.see(index)
        self._load_protocol(self.parent.protocols[index])

    def _on_select(self, _event=None):
        selection = self.protocol_list.curselection()
        if selection:
            self._load_protocol(self.parent.protocols[selection[0]])

    def _load_protocol(self, protocol):
        protocol = normalize_protocol(protocol)
        self.original_name = protocol["name"]
        self.protocol_name_var.set(protocol["name"])
        for channel, fields in self.channel_fields.items():
            config = protocol["channels"].get(str(channel))
            fields["enabled"].set(bool(config))
            fields["data_name"].set(config["data_name"] if config else "")
            fields["gain"].set(config["gain"] if config else "1")
            fields["bias"].set(config["bias"] if config else "0")
            fields["unit"].set(config["unit"] if config else "")
            fields["display_ticks"].set(config["display_ticks"] if config else "[]")

    def _new_protocol(self):
        self.original_name = None
        self.protocol_list.selection_clear(0, "end")
        self.protocol_name_var.set("")
        for fields in self.channel_fields.values():
            fields["enabled"].set(False)
            fields["data_name"].set("")
            fields["gain"].set("1")
            fields["bias"].set("0")
            fields["unit"].set("")
            fields["display_ticks"].set("[]")

    def _protocol_from_fields(self):
        channels = {}
        for channel, fields in self.channel_fields.items():
            channels[str(channel)] = {
                "enabled": fields["enabled"].get(),
                "data_name": fields["data_name"].get(),
                "gain": fields["gain"].get(),
                "bias": fields["bias"].get(),
                "unit": fields["unit"].get(),
                "display_ticks": fields["display_ticks"].get(),
            }
        return normalize_protocol({"name": self.protocol_name_var.get(), "channels": channels})

    def _save_protocol(self):
        try:
            protocol = self._protocol_from_fields()
        except ValueError as exc:
            messagebox.showerror("协议格式错误", str(exc), parent=self)
            return

        for existing in self.parent.protocols:
            if existing["name"] == protocol["name"] and existing["name"] != self.original_name:
                messagebox.showerror("协议名称重复", "请使用不同的协议名称。", parent=self)
                return

        if self.original_name is None:
            self.parent.protocols.append(protocol)
        else:
            index = next(
                (i for i, item in enumerate(self.parent.protocols) if item["name"] == self.original_name),
                None,
            )
            if index is None:
                self.parent.protocols.append(protocol)
            else:
                self.parent.protocols[index] = protocol
            if self.parent.selected_protocol_var.get() == self.original_name:
                self.parent.selected_protocol_var.set(protocol["name"])

        self.original_name = protocol["name"]
        self.parent._protocols_changed()
        self._refresh_list()
        self._select_protocol(protocol["name"])

    def _delete_protocol(self):
        if not self.original_name:
            return
        if not messagebox.askyesno("删除协议", f"确定删除“{self.original_name}”吗？", parent=self):
            return
        self.parent.protocols = [
            protocol for protocol in self.parent.protocols if protocol["name"] != self.original_name
        ]
        if self.parent.selected_protocol_var.get() == self.original_name:
            self.parent.selected_protocol_var.set(NO_PROTOCOL)
        self.parent._protocols_changed()
        self._new_protocol()
        self._refresh_list()


class Stick88ScopeApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"stick88 v{APP_VERSION}")
        self.geometry("640x520")
        self.minsize(560, 420)

        self.events = queue.Queue()
        self.worker = None
        self.current_png_path = None
        self.progress_var = tk.DoubleVar(value=0)

        self.settings = self._load_settings()
        self.output_root_var = tk.StringVar(value=self.settings["output_root"])
        self.protocols = self.settings["protocols"]
        self.selected_protocol_var = tk.StringVar(value=self.settings["selected_protocol"])
        self.channel_vars = {
            channel: tk.BooleanVar(value=channel in self.settings["channels"])
            for channel in [1, 2, 3, 4]
        }
        self.active_channels = []

        self._build_ui()
        self._load_note()
        self.after(100, self._drain_events)

    def _load_settings(self):
        default = {
            "output_root": str(DEFAULT_OUTPUT_ROOT),
            "markdown_text": "# 实验记录\n\n",
            "save_percent": 100,
            "channels": [1, 2, 3],
            "protocols": copy.deepcopy(DEFAULT_PROTOCOLS),
            "selected_protocol": NO_PROTOCOL,
        }
        if not SETTINGS_PATH.exists():
            return default
        try:
            with SETTINGS_PATH.open("r", encoding="utf-8") as f:
                loaded = json.load(f)
            default.update(loaded)
        except Exception:
            pass
        try:
            default["protocols"] = normalize_protocols(default.get("protocols", []))
        except ValueError:
            default["protocols"] = normalize_protocols(copy.deepcopy(DEFAULT_PROTOCOLS))
        protocol_names = {protocol["name"] for protocol in default["protocols"]}
        if default.get("selected_protocol") not in protocol_names:
            default["selected_protocol"] = NO_PROTOCOL
        return default

    def _save_settings(self):
        settings = {
            "output_root": self.output_root_var.get().strip() or str(DEFAULT_OUTPUT_ROOT),
            "markdown_text": self.note_text.get("1.0", "end-1c") if hasattr(self, "note_text") else self.settings.get("markdown_text", ""),
            "save_percent": 100,
            "channels": self._selected_channels() if hasattr(self, "channel_vars") else self.settings.get("channels", [1, 2, 3]),
            "protocols": protocols_for_storage(self.protocols),
            "selected_protocol": self.selected_protocol_var.get(),
        }
        SETTINGS_PATH.write_text(json.dumps(settings, indent=2, ensure_ascii=False), encoding="utf-8")
        self.settings = settings

    def _build_ui(self):
        root = ttk.Frame(self, padding=10)
        root.pack(fill="both", expand=True)
        root.columnconfigure(0, weight=1, minsize=310)
        root.columnconfigure(1, weight=1, minsize=230)
        root.rowconfigure(0, weight=1)

        left = ttk.Frame(root)
        right = ttk.Frame(root)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        right.grid(row=0, column=1, sticky="nsew", padx=(8, 0))

        self._build_left_column(left)
        self._build_right_column(right)

    def _build_left_column(self, parent):
        parent.columnconfigure(0, weight=1)

        output_frame = ttk.LabelFrame(parent, text="保存位置", padding=8)
        output_frame.grid(row=0, column=0, sticky="ew")
        output_frame.columnconfigure(0, weight=1)

        self.output_entry = ttk.Entry(output_frame, textvariable=self.output_root_var)
        self.output_entry.grid(row=0, column=0, columnspan=2, sticky="ew")
        self.output_entry.bind("<FocusOut>", lambda _event: self._on_output_changed())
        self.output_entry.bind("<Return>", lambda _event: self._on_output_changed())
        ttk.Button(output_frame, text="选择", command=self._choose_output_root).grid(row=1, column=0, sticky="ew", pady=(6, 0), padx=(0, 4))
        ttk.Button(output_frame, text="记忆", command=self._on_output_changed).grid(row=1, column=1, sticky="ew", pady=(6, 0))

        channel_frame = ttk.LabelFrame(parent, text="保存通道", padding=8)
        channel_frame.grid(row=1, column=0, sticky="ew", pady=(8, 0))
        for index, channel in enumerate([1, 2, 3, 4]):
            ttk.Checkbutton(
                channel_frame,
                text=f"CH{channel}",
                variable=self.channel_vars[channel],
                command=self._on_channels_changed,
            ).grid(row=index // 2, column=index % 2, sticky="w", padx=(0, 18), pady=2)

        protocol_frame = ttk.LabelFrame(parent, text="数据换算协议", padding=8)
        protocol_frame.grid(row=2, column=0, sticky="ew", pady=(8, 0))
        protocol_frame.columnconfigure(0, weight=1)
        self.protocol_combo = ttk.Combobox(
            protocol_frame,
            textvariable=self.selected_protocol_var,
            state="readonly",
        )
        self.protocol_combo.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        self.protocol_combo.bind("<<ComboboxSelected>>", lambda _event: self._on_protocol_selected())
        ttk.Button(protocol_frame, text="管理", command=self._manage_protocols).grid(row=0, column=1)
        self.protocol_summary_var = tk.StringVar()
        ttk.Label(protocol_frame, textvariable=self.protocol_summary_var, foreground="#555555", wraplength=280).grid(
            row=1, column=0, columnspan=2, sticky="w", pady=(6, 0)
        )
        self._refresh_protocol_combo()

        note_frame = ttk.LabelFrame(parent, text="Markdown 文本区（保存到本次数据文件夹 README.md）", padding=8)
        note_frame.grid(row=3, column=0, sticky="nsew", pady=(8, 0))
        note_frame.rowconfigure(0, weight=1)
        note_frame.columnconfigure(0, weight=1)

        self.note_text = tk.Text(note_frame, wrap="word", undo=True, height=12)
        self.note_text.grid(row=0, column=0, sticky="nsew")
        note_scroll = ttk.Scrollbar(note_frame, command=self.note_text.yview)
        note_scroll.grid(row=0, column=1, sticky="ns")
        self.note_text.configure(yscrollcommand=note_scroll.set)

        parent.rowconfigure(3, weight=1)

        self.save_button = ttk.Button(parent, text="保存数据并绘图", command=self._start_save)
        self.save_button.grid(row=4, column=0, sticky="ew", pady=(8, 0))

    def _build_right_column(self, parent):
        parent.rowconfigure(2, weight=1)
        parent.columnconfigure(0, weight=1)

        progress_frame = ttk.LabelFrame(parent, text="保存进度", padding=8)
        progress_frame.grid(row=0, column=0, sticky="ew")
        progress_frame.columnconfigure(0, weight=1)
        self.progress_bar = ttk.Progressbar(progress_frame, variable=self.progress_var, maximum=100, mode="determinate")
        self.progress_bar.grid(row=0, column=0, sticky="ew")
        self.progress_text = tk.StringVar(value="0%")
        ttk.Label(progress_frame, textvariable=self.progress_text, width=6).grid(row=0, column=1, padx=(6, 0))

        info_frame = ttk.LabelFrame(parent, text="输出信息", padding=8)
        info_frame.grid(row=1, column=0, sticky="ew", pady=(8, 0))
        info_frame.columnconfigure(0, weight=1)
        self.status_var = tk.StringVar(value="等待保存")
        ttk.Label(info_frame, textvariable=self.status_var).grid(row=0, column=0, sticky="w")
        self.output_var = tk.StringVar(value=f"保存目录: {self.output_root_var.get()}")
        ttk.Label(info_frame, textvariable=self.output_var, wraplength=220).grid(row=1, column=0, sticky="w", pady=(4, 0))
        self.png_link_var = tk.StringVar(value="波形图片: 尚未生成")
        self.png_link = ttk.Label(info_frame, textvariable=self.png_link_var, foreground="#0b62a3", cursor="hand2", wraplength=220)
        self.png_link.grid(row=2, column=0, sticky="w", pady=(4, 0))
        self.png_link.bind("<Button-1>", lambda _event: self._open_png())

        log_frame = ttk.LabelFrame(parent, text="运行日志", padding=8)
        log_frame.grid(row=2, column=0, sticky="nsew", pady=(8, 0))
        log_frame.rowconfigure(0, weight=1)
        log_frame.columnconfigure(0, weight=1)
        self.log_text = tk.Text(log_frame, wrap="word", height=12)
        self.log_text.grid(row=0, column=0, sticky="nsew")
        log_scroll = ttk.Scrollbar(log_frame, command=self.log_text.yview)
        log_scroll.grid(row=0, column=1, sticky="ns")
        self.log_text.configure(yscrollcommand=log_scroll.set)

    def _choose_output_root(self):
        initial = self.output_root_var.get().strip() or str(DEFAULT_OUTPUT_ROOT)
        selected = filedialog.askdirectory(initialdir=initial)
        if selected:
            self.output_root_var.set(selected)
            self._on_output_changed()

    def _on_output_changed(self):
        self._save_settings()
        self.output_var.set(f"保存目录: {self.output_root_var.get()}")
        self._log(f"保存目录已更新: {self.output_root_var.get()}\n")

    def _refresh_protocol_combo(self):
        names = [NO_PROTOCOL] + [protocol["name"] for protocol in self.protocols]
        self.protocol_combo.configure(values=names)
        if self.selected_protocol_var.get() not in names:
            self.selected_protocol_var.set(NO_PROTOCOL)
        self._update_protocol_summary()

    def _update_protocol_summary(self):
        protocol = find_protocol(self.protocols, self.selected_protocol_var.get())
        if not protocol:
            self.protocol_summary_var.set("保存并绘制示波器原始数值")
            return
        parts = [
            f"CH{channel}: {config['data_name']} [{config['unit']}]"
            for channel, config in sorted(protocol["channels"].items())
        ]
        self.protocol_summary_var.set("；".join(parts))

    def _on_protocol_selected(self):
        self._update_protocol_summary()
        self._save_settings()
        self._log(f"当前协议: {self.selected_protocol_var.get()}\n")

    def _manage_protocols(self):
        ProtocolManagerDialog(self)

    def _protocols_changed(self):
        self.protocols = normalize_protocols(self.protocols)
        self._refresh_protocol_combo()
        self._save_settings()

    def _selected_channels(self):
        return [channel for channel in [1, 2, 3, 4] if self.channel_vars[channel].get()]

    def _on_channels_changed(self):
        channels = self._selected_channels()
        if channels:
            self._save_settings()
            self._log(f"保存通道已更新: {', '.join(f'CH{channel}' for channel in channels)}\n")

    def _load_note(self):
        if self.settings.get("markdown_text"):
            self.note_text.insert("1.0", self.settings["markdown_text"])
        elif OLD_README_PATH.exists():
            self.note_text.insert("1.0", OLD_README_PATH.read_text(encoding="utf-8"))
        elif OLD_NOTE_PATH.exists():
            self.note_text.insert("1.0", OLD_NOTE_PATH.read_text(encoding="utf-8"))
        else:
            self.note_text.insert("1.0", "# 实验记录\n\n")

    def _save_note_content(self, content, output_folder=None):
        self._save_settings()
        if output_folder is not None:
            Path(output_folder, "README.md").write_text(content, encoding="utf-8")

    def _start_save(self):
        if self.worker and self.worker.is_alive():
            messagebox.showinfo("正在运行", "保存任务还没有结束。")
            return

        note_content = self.note_text.get("1.0", "end-1c")
        channels = self._selected_channels()
        if not channels:
            messagebox.showerror("未选择通道", "请至少勾选一个通道。")
            return

        self.active_channels = channels
        protocol = find_protocol(self.protocols, self.selected_protocol_var.get())
        self.current_png_path = None
        self.png_link_var.set("波形图片: 正在等待生成")
        self._save_note_content(note_content)
        self._save_settings()

        output_root = Path(self.output_root_var.get().strip() or str(DEFAULT_OUTPUT_ROOT))
        self.output_var.set(f"保存目录: {output_root}")
        self._set_progress(0)
        self.save_button.configure(state="disabled")
        self.status_var.set("正在保存示波器数据...")
        self._log("\n=== 开始保存 ===\n")

        self.worker = threading.Thread(
            target=self._save_worker,
            args=(output_root, note_content, channels, protocol),
            daemon=True,
        )
        self.worker.start()

    def _save_worker(self, output_root, note_content, channels, protocol):
        writer = QueueWriter(self.events)
        try:
            config = load_config()
            max_points = config.get("max_points")
            tmctl_dir = config.get("tmctl_dir")

            with contextlib.redirect_stdout(writer), contextlib.redirect_stderr(writer):
                output_folder = save_waveforms(
                    tmctl_dir=tmctl_dir,
                    output_root=output_root,
                    channels=channels,
                    max_points=max_points,
                    save_percent=100,
                    protocol=protocol,
                )
                self._save_note_content(note_content, output_folder)
                png_path = plot_folder(output_folder)
                print(f"Saved plot: {png_path}", flush=True)
                print(f"PNG size: {png_path.stat().st_size / 1024:.1f} KB", flush=True)

            self.events.put(("done", output_folder, png_path))
        except Exception as exc:
            self.events.put(("error", str(exc)))

    def _drain_events(self):
        while True:
            try:
                event = self.events.get_nowait()
            except queue.Empty:
                break

            kind = event[0]
            if kind == "log":
                self._log(event[1])
                self._update_progress_from_log(event[1])
            elif kind == "done":
                output_folder, png_path = event[1], event[2]
                self.status_var.set("数据已保存完毕")
                self.output_var.set(f"本次输出: {output_folder}")
                self._set_progress(100)
                self.save_button.configure(state="normal")
                self._log("数据已保存完毕\n")
                self._set_png_link(png_path)
            elif kind == "error":
                self.status_var.set("保存失败")
                self.save_button.configure(state="normal")
                self._log(f"ERROR: {event[1]}\n")
                messagebox.showerror("保存失败", event[1])

        self.after(100, self._drain_events)

    def _set_png_link(self, png_path):
        self.current_png_path = Path(png_path)
        self.png_link_var.set(f"打开波形图片: {self.current_png_path.name}")

    def _open_png(self):
        if not self.current_png_path or not self.current_png_path.exists():
            messagebox.showinfo("暂无图片", "还没有生成可打开的波形图片。")
            return
        os.startfile(str(self.current_png_path))

    def _log(self, text):
        self.log_text.insert("end", text)
        self.log_text.see("end")

    def _set_progress(self, value):
        value = max(0, min(100, value))
        self.progress_var.set(value)
        self.progress_text.set(f"{int(value)}%")

    def _update_progress_from_log(self, text):
        if not self.active_channels:
            return
        for index, channel in enumerate(self.active_channels, start=1):
            if f"Saved CH{channel}" in text:
                self._set_progress(index / len(self.active_channels) * 100)


def main():
    app = Stick88ScopeApp()
    app.mainloop()


if __name__ == "__main__":
    main()
