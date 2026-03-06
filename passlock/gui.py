"""
PassLock GUI — Cross-platform graphical interface using tkinter.
"""

import platform
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from pathlib import Path

from passlock import __version__, __app_name__
from passlock.core import (
    ENCRYPTED_EXT,
    encrypt_file,
    encrypt_folder,
    smart_unlock,
)
from passlock.logger import (
    log_activity,
    get_activity_log,
    clear_activity_log,
    save_password_entry,
    get_password_history,
    clear_password_history,
    get_purge_schedule,
    set_purge_schedule,
    auto_purge,
    PURGE_OPTIONS,
)

# ── Theme colours ─────────────────────────────────────────────────────

_IS_DARK = False  # default; detected at runtime where possible

COLORS = {
    "bg":          "#f5f5f5",
    "fg":          "#1e1e1e",
    "accent":      "#2563eb",
    "accent_fg":   "#ffffff",
    "danger":      "#dc2626",
    "danger_fg":   "#ffffff",
    "success":     "#16a34a",
    "card_bg":     "#ffffff",
    "entry_bg":    "#ffffff",
    "entry_fg":    "#1e1e1e",
    "border":      "#d1d5db",
    "muted":       "#6b7280",
}


def _apply_os_tweaks(root: tk.Tk) -> None:
    """Apply per-OS visual tweaks."""
    system = platform.system()
    if system == "Darwin":
        # macOS: use aqua look, bigger default font
        try:
            root.tk.call("::tk::unsupported::MacWindowStyle", "style", root._w, "document", "closeBox collapseBox")
        except tk.TclError:
            pass
    elif system == "Windows":
        try:
            from ctypes import windll
            windll.shcore.SetProcessDpiAwareness(1)  # crisp text on HiDPI
        except Exception:
            pass


# ── Password dialog ──────────────────────────────────────────────────

class PasswordDialog(tk.Toplevel):
    """Modal dialog that asks for a password (with optional confirmation)."""

    def __init__(self, parent: tk.Tk, *, confirm: bool = False, title: str = "Enter Password"):
        super().__init__(parent)
        self.title(title)
        self.resizable(False, False)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self._on_cancel)

        self.result: str | None = None
        self._confirm = confirm

        frame = ttk.Frame(self, padding=20)
        frame.pack(fill="both", expand=True)

        ttk.Label(frame, text="Password:").grid(row=0, column=0, sticky="w", pady=(0, 4))
        self._pw1 = ttk.Entry(frame, show="•", width=32)
        self._pw1.grid(row=1, column=0, pady=(0, 10))
        self._pw1.focus_set()

        if confirm:
            ttk.Label(frame, text="Confirm password:").grid(row=2, column=0, sticky="w", pady=(0, 4))
            self._pw2 = ttk.Entry(frame, show="•", width=32)
            self._pw2.grid(row=3, column=0, pady=(0, 10))

        btn_frame = ttk.Frame(frame)
        btn_frame.grid(row=4, column=0, pady=(6, 0))
        ttk.Button(btn_frame, text="OK", command=self._on_ok, width=10).pack(side="left", padx=(0, 8))
        ttk.Button(btn_frame, text="Cancel", command=self._on_cancel, width=10).pack(side="left")

        self._pw1.bind("<Return>", lambda e: self._on_ok())

        # Centre on parent
        self.update_idletasks()
        x = parent.winfo_x() + (parent.winfo_width() - self.winfo_width()) // 2
        y = parent.winfo_y() + (parent.winfo_height() - self.winfo_height()) // 2
        self.geometry(f"+{x}+{y}")

        self.wait_window()

    def _on_ok(self) -> None:
        pw = self._pw1.get()
        if len(pw) < 4:
            messagebox.showwarning("Weak password", "Password must be at least 4 characters.", parent=self)
            return
        if self._confirm:
            if pw != self._pw2.get():
                messagebox.showwarning("Mismatch", "Passwords do not match.", parent=self)
                return
        self.result = pw
        self.destroy()

    def _on_cancel(self) -> None:
        self.result = None
        self.destroy()


# ── Main application window ──────────────────────────────────────────

class PassLockApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(f"{__app_name__} v{__version__}")
        self.minsize(460, 420)
        _apply_os_tweaks(self)

        # Maximize window on launch
        system = platform.system()
        if system == "Darwin":
            self.state("zoomed")
        elif system == "Windows":
            self.state("zoomed")
        else:
            self.attributes("-zoomed", True)

        # Style
        style = ttk.Style(self)
        available = style.theme_names()
        # Prefer clam/alt for a cleaner look across platforms
        for theme in ("clam", "alt", "default"):
            if theme in available:
                style.theme_use(theme)
                break

        style.configure("Accent.TButton", font=("Helvetica", 11, "bold"))
        style.configure("Header.TLabel", font=("Helvetica", 16, "bold"))
        style.configure("Sub.TLabel", font=("Helvetica", 10))
        style.configure("Status.TLabel", font=("Helvetica", 10))

        self._build_ui()

    # ── UI construction ──────────────────────────────────────────────

    def _build_ui(self) -> None:
        container = ttk.Frame(self, padding=18)
        container.pack(fill="both", expand=True)

        # Header
        ttk.Label(container, text=f"🔒 {__app_name__}", style="Header.TLabel").pack(anchor="w")
        ttk.Label(
            container,
            text="Password-protect your files & folders with AES-256 encryption",
            style="Sub.TLabel",
        ).pack(anchor="w", pady=(2, 16))

        # ── Target selection ─────────────────────────────────────────
        target_frame = ttk.LabelFrame(container, text="Target", padding=10)
        target_frame.pack(fill="x", pady=(0, 10))

        row = ttk.Frame(target_frame)
        row.pack(fill="x")

        self._target_var = tk.StringVar()
        self._target_entry = ttk.Entry(row, textvariable=self._target_var)
        self._target_entry.pack(side="left", fill="x", expand=True, padx=(0, 6))

        ttk.Button(row, text="File…", width=7, command=self._browse_file).pack(side="left", padx=(0, 4))
        ttk.Button(row, text="Folder…", width=7, command=self._browse_folder).pack(side="left")

        # ── Action buttons ───────────────────────────────────────────
        btn_frame = ttk.Frame(container)
        btn_frame.pack(fill="x", pady=(6, 10))

        self._lock_btn = ttk.Button(btn_frame, text="🔐  Lock", style="Accent.TButton", command=self._on_lock)
        self._lock_btn.pack(side="left", expand=True, fill="x", padx=(0, 6), ipady=6)

        self._unlock_btn = ttk.Button(btn_frame, text="🔓  Unlock", style="Accent.TButton", command=self._on_unlock)
        self._unlock_btn.pack(side="left", expand=True, fill="x", padx=(6, 0), ipady=6)

        # ── Progress ─────────────────────────────────────────────────
        self._progress = ttk.Progressbar(container, mode="indeterminate")
        self._progress.pack(fill="x", pady=(0, 6))

        # ── Tabbed area (Status Log / Activity History / Password History / Settings) ──
        notebook = ttk.Notebook(container)
        notebook.pack(fill="both", expand=True, pady=(0, 4))

        # Tab 1: Status log
        log_frame = ttk.Frame(notebook, padding=6)
        notebook.add(log_frame, text="Status")

        self._log = tk.Text(log_frame, height=8, wrap="word", state="disabled", font=("Courier", 10))
        scrollbar = ttk.Scrollbar(log_frame, command=self._log.yview)
        self._log.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self._log.pack(fill="both", expand=True)

        # Tab 2: Activity history
        activity_frame = ttk.Frame(notebook, padding=6)
        notebook.add(activity_frame, text="Activity Log")

        act_btn_row = ttk.Frame(activity_frame)
        act_btn_row.pack(fill="x", pady=(0, 4))
        ttk.Button(act_btn_row, text="Refresh", command=self._refresh_activity_log).pack(side="left", padx=(0, 6))
        ttk.Button(act_btn_row, text="Clear All", command=self._clear_activity_log).pack(side="left")

        self._activity_text = tk.Text(activity_frame, height=8, wrap="word", state="disabled", font=("Courier", 10))
        act_scroll = ttk.Scrollbar(activity_frame, command=self._activity_text.yview)
        self._activity_text.configure(yscrollcommand=act_scroll.set)
        act_scroll.pack(side="right", fill="y")
        self._activity_text.pack(fill="both", expand=True)

        # Tab 3: Password history
        pw_history_frame = ttk.Frame(notebook, padding=6)
        notebook.add(pw_history_frame, text="Password History")

        pw_btn_row = ttk.Frame(pw_history_frame)
        pw_btn_row.pack(fill="x", pady=(0, 4))
        ttk.Button(pw_btn_row, text="Refresh", command=self._refresh_pw_history).pack(side="left", padx=(0, 6))
        ttk.Button(pw_btn_row, text="Clear All", command=self._clear_pw_history).pack(side="left")

        self._pw_history_text = tk.Text(pw_history_frame, height=8, wrap="word", state="disabled", font=("Courier", 10))
        pw_scroll = ttk.Scrollbar(pw_history_frame, command=self._pw_history_text.yview)
        self._pw_history_text.configure(yscrollcommand=pw_scroll.set)
        pw_scroll.pack(side="right", fill="y")
        self._pw_history_text.pack(fill="both", expand=True)

        # Tab 4: Settings (purge schedule)
        settings_frame = ttk.Frame(notebook, padding=10)
        notebook.add(settings_frame, text="Settings")

        ttk.Label(settings_frame, text="Auto-purge activity logs:", font=("Helvetica", 11)).pack(anchor="w", pady=(0, 6))

        self._purge_var = tk.StringVar(value=get_purge_schedule())
        for label, key in [("Daily", "daily"), ("Weekly", "weekly"), ("Bi-weekly", "biweekly"), ("Monthly", "monthly"), ("Never", "never")]:
            ttk.Radiobutton(settings_frame, text=label, variable=self._purge_var, value=key,
                            command=self._on_purge_change).pack(anchor="w", padx=10, pady=2)

        ttk.Separator(settings_frame, orient="horizontal").pack(fill="x", pady=10)
        ttk.Button(settings_frame, text="Purge Old Logs Now", command=self._purge_now).pack(anchor="w")

        # OS info footer
        sys_info = f"{platform.system()} {platform.release()} • Python {platform.python_version()}"
        ttk.Label(container, text=sys_info, style="Status.TLabel", foreground="gray").pack(anchor="e", pady=(4, 0))

    # ── Helpers ──────────────────────────────────────────────────────

    def _log_msg(self, msg: str) -> None:
        self._log.configure(state="normal")
        self._log.insert("end", msg + "\n")
        self._log.see("end")
        self._log.configure(state="disabled")

    def _set_busy(self, busy: bool) -> None:
        state = "disabled" if busy else "normal"
        self._lock_btn.configure(state=state)
        self._unlock_btn.configure(state=state)
        if busy:
            self._progress.start(12)
        else:
            self._progress.stop()

    def _browse_file(self) -> None:
        path = filedialog.askopenfilename(title="Select a file")
        if path:
            self._target_var.set(path)

    def _browse_folder(self) -> None:
        path = filedialog.askdirectory(title="Select a folder")
        if path:
            self._target_var.set(path)

    def _get_target(self) -> Path | None:
        raw = self._target_var.get().strip()
        if not raw:
            messagebox.showwarning("No target", "Select a file or folder first.")
            return None
        p = Path(raw).resolve()
        if not p.exists():
            messagebox.showerror("Not found", f"'{p}' does not exist.")
            return None
        return p

    # ── Lock action ──────────────────────────────────────────────────

    def _on_lock(self) -> None:
        target = self._get_target()
        if target is None:
            return

        dlg = PasswordDialog(self, confirm=True, title="Set Lock Password")
        if dlg.result is None:
            return
        password = dlg.result
        self._set_busy(True)
        self._log_msg(f"Locking: {target} …")

        def task():
            try:
                if target.is_file():
                    out = encrypt_file(target, password, remove_original=True)
                elif target.is_dir():
                    out = encrypt_folder(target, password, remove_original=True)
                else:
                    raise ValueError("Target is neither a file nor a directory.")
                save_password_entry(str(target), password)
                log_activity("Lock", str(target), f"Success → {out}")
                self.after(0, lambda: self._on_done(f"✅ Locked → {out}"))
            except Exception as exc:
                log_activity("Lock", str(target), f"Error: {exc}")
                self.after(0, lambda: self._on_error(str(exc)))

        threading.Thread(target=task, daemon=True).start()

    # ── Unlock action ────────────────────────────────────────────────

    def _on_unlock(self) -> None:
        target = self._get_target()
        if target is None:
            return
        if not target.is_file():
            messagebox.showerror("Invalid", "Unlock target must be a .locked file.")
            return

        dlg = PasswordDialog(self, confirm=False, title="Enter Unlock Password")
        if dlg.result is None:
            return
        password = dlg.result

        self._set_busy(True)
        self._log_msg(f"Unlocking: {target} …")

        def task():
            try:
                out = smart_unlock(target, password, remove_encrypted=True)
                log_activity("Unlock", str(target), f"Success → {out}")
                self.after(0, lambda: self._on_done(f"✅ Unlocked → {out}"))
            except Exception as exc:
                log_activity("Unlock", str(target), f"Error: {exc}")
                self.after(0, lambda: self._on_error(str(exc)))

        threading.Thread(target=task, daemon=True).start()

    # ── Callbacks ────────────────────────────────────────────────────

    def _on_done(self, msg: str) -> None:
        self._set_busy(False)
        self._log_msg(msg)

    def _on_error(self, msg: str) -> None:
        self._set_busy(False)
        self._log_msg(f"❌ Error: {msg}")
        messagebox.showerror("Error", msg)

    # ── Activity log helpers ─────────────────────────────────────────

    def _refresh_activity_log(self) -> None:
        entries = get_activity_log()
        self._activity_text.configure(state="normal")
        self._activity_text.delete("1.0", "end")
        if not entries:
            self._activity_text.insert("end", "No activity recorded yet.\n")
        else:
            for e in reversed(entries):
                line = f"[{e.get('timestamp', '?')}]  {e.get('action', '?')}  |  {e.get('target', '?')}  |  {e.get('result', '')}\n"
                self._activity_text.insert("end", line)
        self._activity_text.configure(state="disabled")

    def _clear_activity_log(self) -> None:
        if messagebox.askyesno("Clear Activity Log", "Delete all activity log entries?"):
            clear_activity_log()
            self._refresh_activity_log()
            self._log_msg("Activity log cleared.")

    # ── Password history helpers ─────────────────────────────────────

    def _refresh_pw_history(self) -> None:
        history = get_password_history()
        self._pw_history_text.configure(state="normal")
        self._pw_history_text.delete("1.0", "end")
        if not history:
            self._pw_history_text.insert("end", "No password history saved yet.\n")
        else:
            for path, entries in history.items():
                self._pw_history_text.insert("end", f"📄 {path}\n")
                for e in entries:
                    ts = e.get("timestamp", "?")
                    pw = e.get("password", "?")
                    self._pw_history_text.insert("end", f"   [{ts}]  password: {pw}\n")
                self._pw_history_text.insert("end", "\n")
        self._pw_history_text.configure(state="disabled")

    def _clear_pw_history(self) -> None:
        if messagebox.askyesno("Clear Password History", "Delete all saved password records?"):
            clear_password_history()
            self._refresh_pw_history()
            self._log_msg("Password history cleared.")

    # ── Settings helpers ─────────────────────────────────────────────

    def _on_purge_change(self) -> None:
        schedule = self._purge_var.get()
        set_purge_schedule(schedule)
        self._log_msg(f"Purge schedule set to: {schedule}")

    def _purge_now(self) -> None:
        removed = auto_purge()
        self._log_msg(f"Purged {removed} old log entries.")
        self._refresh_activity_log()


# ── Entry point ──────────────────────────────────────────────────────

def launch_gui() -> None:
    auto_purge()  # purge old logs based on saved schedule
    app = PassLockApp()
    app.mainloop()


if __name__ == "__main__":
    launch_gui()
