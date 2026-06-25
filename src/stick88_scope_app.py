import contextlib
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
APP_VERSION = "1.1.0"

from plot_saved_waveforms_png import plot_folder
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
        self.save_percent_var = tk.IntVar(value=self.settings["save_percent"])
        self.save_percent_entry_var = tk.StringVar(value=str(self.settings["save_percent"]))
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
        }
        if not SETTINGS_PATH.exists():
            return default
        try:
            with SETTINGS_PATH.open("r", encoding="utf-8") as f:
                loaded = json.load(f)
            default.update(loaded)
        except Exception:
            pass
        return default

    def _save_settings(self):
        settings = {
            "output_root": self.output_root_var.get().strip() or str(DEFAULT_OUTPUT_ROOT),
            "markdown_text": self.note_text.get("1.0", "end-1c") if hasattr(self, "note_text") else self.settings.get("markdown_text", ""),
            "save_percent": self._get_save_percent(),
            "channels": self._selected_channels() if hasattr(self, "channel_vars") else self.settings.get("channels", [1, 2, 3]),
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

        percent_frame = ttk.LabelFrame(parent, text="保存数据长度比例", padding=8)
        percent_frame.grid(row=2, column=0, sticky="ew", pady=(8, 0))
        percent_frame.columnconfigure(0, weight=1)
        self.percent_scale = ttk.Scale(
            percent_frame,
            from_=1,
            to=100,
            orient="horizontal",
            variable=self.save_percent_var,
            command=self._on_percent_slider,
        )
        self.percent_scale.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        self.percent_entry = ttk.Entry(percent_frame, textvariable=self.save_percent_entry_var, width=6)
        self.percent_entry.grid(row=0, column=1)
        self.percent_entry.bind("<Return>", lambda _event: self._on_percent_entry())
        self.percent_entry.bind("<FocusOut>", lambda _event: self._on_percent_entry())
        ttk.Label(percent_frame, text="%").grid(row=0, column=2, sticky="w", padx=(4, 0))

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

    def _get_save_percent(self):
        try:
            value = int(float(self.save_percent_entry_var.get().strip()))
        except ValueError:
            value = int(self.save_percent_var.get())
        return max(1, min(100, value))

    def _set_save_percent(self, value, save=True):
        value = max(1, min(100, int(round(float(value)))))
        self.save_percent_var.set(value)
        self.save_percent_entry_var.set(str(value))
        if save:
            self._save_settings()

    def _on_percent_slider(self, value):
        self._set_save_percent(value, save=False)

    def _on_percent_entry(self):
        self._set_save_percent(self._get_save_percent(), save=True)
        self._log(f"保存比例已更新: {self.save_percent_entry_var.get()}%\n")

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
        save_percent = self._get_save_percent()
        channels = self._selected_channels()
        if not channels:
            messagebox.showerror("未选择通道", "请至少勾选一个通道。")
            return

        self.active_channels = channels
        self.current_png_path = None
        self.png_link_var.set("波形图片: 正在等待生成")
        self._set_save_percent(save_percent)
        self._save_note_content(note_content)
        self._save_settings()

        output_root = Path(self.output_root_var.get().strip() or str(DEFAULT_OUTPUT_ROOT))
        self.output_var.set(f"保存目录: {output_root}")
        self._set_progress(0)
        self.save_button.configure(state="disabled")
        self.status_var.set("正在保存示波器数据...")
        self._log("\n=== 开始保存 ===\n")

        self.worker = threading.Thread(target=self._save_worker, args=(output_root, note_content, save_percent, channels), daemon=True)
        self.worker.start()

    def _save_worker(self, output_root, note_content, save_percent, channels):
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
                    save_percent=save_percent,
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
