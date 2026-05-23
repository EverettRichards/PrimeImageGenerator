from __future__ import annotations

import queue
import threading
import tkinter as tk
from dataclasses import replace
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText

from PIL import Image, ImageTk

from .engine import GenerationSettings, generate_ascii_art, RESAMPLING_LANCZOS

PROJECT_ROOT = Path(__file__).resolve().parents[1]


class AsciiGeneratorApp:
    def __init__(self, root: tk.Tk, app_title: str = "VADIM ASCII Generator") -> None:
        self.root = root
        self.root.title(app_title)
        self.root.geometry("1280x860")
        self.root.minsize(1100, 760)

        self.message_queue: queue.Queue[tuple[str, object]] = queue.Queue()
        self.current_image_path: str | None = None
        self.current_result = None
        self.preview_photo: ImageTk.PhotoImage | None = None
        self.worker_running = False

        self.image_path_var = tk.StringVar(value="No image selected")
        self.sample_width_var = tk.StringVar(value="80")
        self.background_color_var = tk.StringVar(value="#ffffff")
        self.text_color_var = tk.StringVar(value="#000000")
        self.grayscale_method_var = tk.StringVar(value="standard")
        self.brightness_modifier_var = tk.StringVar(value="1.0")
        self.auto_generate_var = tk.BooleanVar(value=True)
        self.bold_var = tk.BooleanVar(value=False)
        self.save_jpg_var = tk.BooleanVar(value=True)
        self.save_pdf_var = tk.BooleanVar(value=False)
        self.save_txt_var = tk.BooleanVar(value=False)
        self.status_var = tk.StringVar(value="Ready")

        self._build_ui()
        self._set_preview_placeholder("Select an image to begin")
        self.root.after(100, self._poll_queue)

    def _build_ui(self) -> None:
        self.root.columnconfigure(0, weight=0)
        self.root.columnconfigure(1, weight=1)
        self.root.rowconfigure(0, weight=1)
        self.root.rowconfigure(1, weight=0)

        left = ttk.Frame(self.root, padding=14)
        left.grid(row=0, column=0, sticky="nsw")
        left.columnconfigure(0, weight=1)

        right = ttk.Frame(self.root, padding=14)
        right.grid(row=0, column=1, sticky="nsew")
        right.rowconfigure(1, weight=1)
        right.columnconfigure(0, weight=1)

        progress_frame = ttk.LabelFrame(self.root, text="Progress", padding=10)
        progress_frame.grid(row=1, column=0, columnspan=2, sticky="nsew", padx=14, pady=(0, 14))
        progress_frame.rowconfigure(0, weight=1)
        progress_frame.columnconfigure(0, weight=1)

        title = ttk.Label(left, text="ASCII Prime Generator", font=("TkDefaultFont", 14, "bold"))
        title.grid(row=0, column=0, sticky="w", pady=(0, 12))

        image_row = ttk.Frame(left)
        image_row.grid(row=1, column=0, sticky="ew", pady=4)
        image_row.columnconfigure(1, weight=1)
        ttk.Button(image_row, text="Select Image", command=self._choose_image).grid(row=0, column=0, sticky="w")
        ttk.Label(image_row, textvariable=self.image_path_var, wraplength=320).grid(row=0, column=1, sticky="w", padx=(10, 0))

        self._add_entry(left, "Output Width", self.sample_width_var, row=2)
        self._add_entry(left, "Background Color", self.background_color_var, row=3)
        self._add_entry(left, "Text Color", self.text_color_var, row=4)
        self._add_entry(left, "Brightness Modifier", self.brightness_modifier_var, row=5)

        method_row = ttk.Frame(left)
        method_row.grid(row=6, column=0, sticky="ew", pady=4)
        method_row.columnconfigure(1, weight=1)
        ttk.Label(method_row, text="Grayscale Method").grid(row=0, column=0, sticky="w")
        method_box = ttk.Combobox(
            method_row,
            textvariable=self.grayscale_method_var,
            values=("standard", "pca"),
            state="readonly",
            width=12,
        )
        method_box.grid(row=0, column=1, sticky="ew", padx=(10, 0))

        ttk.Checkbutton(left, text="Auto generate", variable=self.auto_generate_var).grid(row=7, column=0, sticky="w", pady=(8, 4))
        ttk.Checkbutton(left, text="Bold text", variable=self.bold_var).grid(row=8, column=0, sticky="w", pady=2)

        save_frame = ttk.LabelFrame(left, text="Save Options", padding=8)
        save_frame.grid(row=9, column=0, sticky="ew", pady=(10, 4))
        ttk.Checkbutton(save_frame, text="Save JPG", variable=self.save_jpg_var).grid(row=0, column=0, sticky="w")
        ttk.Checkbutton(save_frame, text="Save PDF", variable=self.save_pdf_var).grid(row=1, column=0, sticky="w")
        ttk.Checkbutton(save_frame, text="Save TXT", variable=self.save_txt_var).grid(row=2, column=0, sticky="w")

        button_row = ttk.Frame(left)
        button_row.grid(row=10, column=0, sticky="ew", pady=(14, 4))
        button_row.columnconfigure(0, weight=1)
        button_row.columnconfigure(1, weight=1)
        button_row.columnconfigure(2, weight=1)
        self.nonprime_button = ttk.Button(button_row, text="Generate Non-prime", command=self._generate_nonprime)
        self.nonprime_button.grid(row=0, column=0, sticky="ew", padx=(0, 4))
        self.prime_button = ttk.Button(button_row, text="Generate Prime", command=self._generate_prime)
        self.prime_button.grid(row=0, column=1, sticky="ew", padx=4)
        self.clear_button = ttk.Button(button_row, text="Clear Log", command=self._clear_log)
        self.clear_button.grid(row=0, column=2, sticky="ew", padx=(4, 0))

        status_row = ttk.Frame(left)
        status_row.grid(row=11, column=0, sticky="ew", pady=(10, 0))
        ttk.Label(status_row, text="Status:").grid(row=0, column=0, sticky="w")
        ttk.Label(status_row, textvariable=self.status_var, wraplength=320).grid(row=0, column=1, sticky="w", padx=(8, 0))

        preview_title = ttk.Label(right, text="Preview", font=("TkDefaultFont", 14, "bold"))
        preview_title.grid(row=0, column=0, sticky="w", pady=(0, 8))

        preview_frame = ttk.Frame(right, width=640, height=480, relief="solid")
        preview_frame.grid(row=1, column=0, sticky="n")
        preview_frame.grid_propagate(False)
        preview_frame.columnconfigure(0, weight=1)
        preview_frame.rowconfigure(0, weight=1)

        self.preview_label = ttk.Label(preview_frame, anchor="center")
        self.preview_label.grid(row=0, column=0, sticky="nsew")

        self.progress_text = ScrolledText(progress_frame, height=12, wrap=tk.WORD)
        self.progress_text.grid(row=0, column=0, sticky="nsew")
        self.progress_text.configure(state="disabled")

    def _add_entry(self, parent: ttk.Frame, label: str, variable: tk.StringVar, row: int) -> None:
        row_frame = ttk.Frame(parent)
        row_frame.grid(row=row, column=0, sticky="ew", pady=4)
        row_frame.columnconfigure(1, weight=1)
        ttk.Label(row_frame, text=label).grid(row=0, column=0, sticky="w")
        ttk.Entry(row_frame, textvariable=variable, width=18).grid(row=0, column=1, sticky="ew", padx=(10, 0))

    def _choose_image(self) -> None:
        path = filedialog.askopenfilename(
            title="Select an image",
            filetypes=[("Image files", "*.png *.jpg *.jpeg"), ("PNG", "*.png"), ("JPEG", "*.jpg *.jpeg")],
        )
        if not path:
            return

        self.current_image_path = path
        self.image_path_var.set(path)
        self._log_line(f"Selected image: {path}")
        if self.auto_generate_var.get():
            self._start_generation(prime_requested=False, auto=True)

    def _generate_nonprime(self) -> None:
        self._start_generation(prime_requested=False, auto=False)

    def _generate_prime(self) -> None:
        self._start_generation(prime_requested=True, auto=False)

    def _parse_settings(self, enforce_primality: bool) -> GenerationSettings:
        if not self.current_image_path:
            raise ValueError("Please select an image first.")

        output_dir = str(PROJECT_ROOT / "outputs")
        return GenerationSettings(
            image_path=self.current_image_path,
            output_dir=output_dir,
            sample_width=max(1, int(float(self.sample_width_var.get()))),
            bold=self.bold_var.get(),
            background_color=self.background_color_var.get().strip(),
            text_color=self.text_color_var.get().strip(),
            grayscale_method=self.grayscale_method_var.get().strip().lower(),
            brightness_modifier=float(self.brightness_modifier_var.get()),
            enforce_primality=enforce_primality,
            save_pdf=self.save_pdf_var.get(),
            save_jpg=self.save_jpg_var.get(),
            save_txt=self.save_txt_var.get(),
            update_interval=15,
        )

    def _start_generation(self, prime_requested: bool, auto: bool) -> None:
        if self.worker_running:
            self._log_line("Generation already in progress.")
            return

        if not self.current_image_path:
            if auto:
                return
            messagebox.showinfo("Select image", "Please select an image first.")
            return

        try:
            settings = self._parse_settings(enforce_primality=prime_requested)
        except Exception as exc:
            messagebox.showerror("Invalid settings", str(exc))
            return

        self._set_status("Generating prime image..." if prime_requested else "Generating non-prime image...")
        self._clear_log()
        self.worker_running = True
        self._set_buttons_enabled(False)

        thread = threading.Thread(target=self._worker_generate, args=(settings,), daemon=True)
        thread.start()

    def _worker_generate(self, settings: GenerationSettings) -> None:
        try:
            result = generate_ascii_art(settings, logger=self._queue_log)
            self.message_queue.put(("result", result))
        except Exception as exc:
            self.message_queue.put(("error", exc))

    def _queue_log(self, message: str) -> None:
        self.message_queue.put(("log", message))

    def _poll_queue(self) -> None:
        try:
            while True:
                item_type, payload = self.message_queue.get_nowait()
                if item_type == "log":
                    self._log_line(str(payload))
                elif item_type == "result":
                    self.current_result = payload
                    self._update_preview(payload.preview_image)
                    self._set_status(f"Done. Checks: {payload.checks}, sieve rejects: {payload.sieve_rejects}")
                    self._set_buttons_enabled(True)
                    self.worker_running = False
                elif item_type == "error":
                    self._set_status("Error")
                    self._set_buttons_enabled(True)
                    self.worker_running = False
                    messagebox.showerror("Generation failed", str(payload))
        except queue.Empty:
            pass
        finally:
            self.root.after(100, self._poll_queue)

    def _update_preview(self, image: Image.Image) -> None:
        preview = image.copy()
        preview.thumbnail((620, 460), RESAMPLING_LANCZOS)
        self.preview_photo = ImageTk.PhotoImage(preview)
        self.preview_label.configure(image=self.preview_photo, text="")

    def _set_preview_placeholder(self, text: str) -> None:
        self.preview_label.configure(image="", text=text, anchor="center")

    def _set_status(self, text: str) -> None:
        self.status_var.set(text)

    def _set_buttons_enabled(self, enabled: bool) -> None:
        state = "normal" if enabled else "disabled"
        self.nonprime_button.configure(state=state)
        self.prime_button.configure(state=state)

    def _log_line(self, line: str) -> None:
        self.progress_text.configure(state="normal")
        self.progress_text.insert(tk.END, line + "\n")
        self.progress_text.see(tk.END)
        self.progress_text.configure(state="disabled")

    def _clear_log(self) -> None:
        self.progress_text.configure(state="normal")
        self.progress_text.delete("1.0", tk.END)
        self.progress_text.configure(state="disabled")


def launch_app(app_title: str = "VADIM ASCII Generator") -> None:
    root = tk.Tk()
    try:
        ttk.Style().theme_use("clam")
    except Exception:
        pass
    AsciiGeneratorApp(root, app_title=app_title)
    root.mainloop()
