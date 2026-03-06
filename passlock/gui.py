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

        style.configure("Accent.TButton", font=("Helvetica", 12, "bold"))
        style.configure("Header.TLabel", font=("Helvetica", 18, "bold"))
        style.configure("Sub.TLabel", font=("Helvetica", 11))
        style.configure("Status.TLabel", font=("Helvetica", 10))
        style.configure("CardHeader.TLabel", font=("Helvetica", 13, "bold"))
        style.configure("TabInfo.TLabel", font=("Helvetica", 11), foreground="#6b7280")

        # Treeview styling for tables
        style.configure("Log.Treeview", font=("Helvetica", 11), rowheight=28)
        style.configure("Log.Treeview.Heading", font=("Helvetica", 11, "bold"))
        style.configure("Activity.Treeview", font=("Helvetica", 11), rowheight=30)
        style.configure("Activity.Treeview.Heading", font=("Helvetica", 11, "bold"))
        style.configure("PwHist.Treeview", font=("Helvetica", 11), rowheight=30)
        style.configure("PwHist.Treeview.Heading", font=("Helvetica", 11, "bold"))

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

        # ── Tabbed area ────────────────────────────────────────────────
        notebook = ttk.Notebook(container)
        notebook.pack(fill="both", expand=True, pady=(0, 4))

        # ── Tab 1: Status log ────────────────────────────────────────
        log_tab = ttk.Frame(notebook, padding=10)
        notebook.add(log_tab, text="  Status  ")

        ttk.Label(log_tab, text="Live Status", style="CardHeader.TLabel").pack(anchor="w", pady=(0, 2))
        ttk.Label(log_tab, text="Real-time status of lock/unlock operations", style="TabInfo.TLabel").pack(anchor="w", pady=(0, 8))

        log_cols = ("time", "message")
        self._log_tree = ttk.Treeview(log_tab, columns=log_cols, show="headings", style="Log.Treeview", height=10)
        self._log_tree.heading("time", text="Time", anchor="w")
        self._log_tree.heading("message", text="Message", anchor="w")
        self._log_tree.column("time", width=160, minwidth=140, stretch=False)
        self._log_tree.column("message", width=600, minwidth=300, stretch=True)

        log_scroll = ttk.Scrollbar(log_tab, orient="vertical", command=self._log_tree.yview)
        self._log_tree.configure(yscrollcommand=log_scroll.set)
        self._log_tree.pack(side="left", fill="both", expand=True)
        log_scroll.pack(side="right", fill="y")

        # Tag colors for status messages
        self._log_tree.tag_configure("success", foreground="#16a34a")
        self._log_tree.tag_configure("error", foreground="#dc2626")
        self._log_tree.tag_configure("info", foreground="#2563eb")

        # ── Tab 2: Activity Log ──────────────────────────────────────
        activity_tab = ttk.Frame(notebook, padding=10)
        notebook.add(activity_tab, text="  Activity Log  ")

        act_header = ttk.Frame(activity_tab)
        act_header.pack(fill="x", pady=(0, 8))

        ttk.Label(act_header, text="Activity History", style="CardHeader.TLabel").pack(side="left")
        ttk.Button(act_header, text="Clear All", command=self._clear_activity_log).pack(side="right", padx=(6, 0))
        ttk.Button(act_header, text="⟳ Refresh", command=self._refresh_activity_log).pack(side="right")

        ttk.Label(activity_tab, text="Complete history of all lock and unlock operations", style="TabInfo.TLabel").pack(anchor="w", pady=(0, 6))

        act_cols = ("timestamp", "action", "target", "result")
        self._activity_tree = ttk.Treeview(activity_tab, columns=act_cols, show="headings", style="Activity.Treeview", height=12)
        self._activity_tree.heading("timestamp", text="Date & Time", anchor="w")
        self._activity_tree.heading("action", text="Action", anchor="center")
        self._activity_tree.heading("target", text="File / Folder", anchor="w")
        self._activity_tree.heading("result", text="Result", anchor="w")
        self._activity_tree.column("timestamp", width=170, minwidth=150, stretch=False)
        self._activity_tree.column("action", width=80, minwidth=70, stretch=False, anchor="center")
        self._activity_tree.column("target", width=350, minwidth=200, stretch=True)
        self._activity_tree.column("result", width=300, minwidth=150, stretch=True)

        self._activity_tree.tag_configure("lock", foreground="#2563eb")
        self._activity_tree.tag_configure("unlock", foreground="#16a34a")
        self._activity_tree.tag_configure("error_row", foreground="#dc2626")

        act_scroll = ttk.Scrollbar(activity_tab, orient="vertical", command=self._activity_tree.yview)
        self._activity_tree.configure(yscrollcommand=act_scroll.set)
        self._activity_tree.pack(side="left", fill="both", expand=True)
        act_scroll.pack(side="right", fill="y")

        # ── Tab 3: Password History ──────────────────────────────────
        pw_tab = ttk.Frame(notebook, padding=10)
        notebook.add(pw_tab, text="  Password History  ")

        pw_header = ttk.Frame(pw_tab)
        pw_header.pack(fill="x", pady=(0, 8))

        ttk.Label(pw_header, text="Saved Passwords", style="CardHeader.TLabel").pack(side="left")
        ttk.Button(pw_header, text="Clear All", command=self._clear_pw_history).pack(side="right", padx=(6, 0))
        ttk.Button(pw_header, text="⟳ Refresh", command=self._refresh_pw_history).pack(side="right")

        ttk.Label(pw_tab, text="Passwords used for each file and folder", style="TabInfo.TLabel").pack(anchor="w", pady=(0, 6))

        pw_cols = ("file", "timestamp", "password")
        self._pw_tree = ttk.Treeview(pw_tab, columns=pw_cols, show="headings", style="PwHist.Treeview", height=12)
        self._pw_tree.heading("file", text="File / Folder", anchor="w")
        self._pw_tree.heading("timestamp", text="Date & Time", anchor="w")
        self._pw_tree.heading("password", text="Password", anchor="w")
        self._pw_tree.column("file", width=380, minwidth=200, stretch=True)
        self._pw_tree.column("timestamp", width=170, minwidth=150, stretch=False)
        self._pw_tree.column("password", width=200, minwidth=120, stretch=True)

        pw_scroll = ttk.Scrollbar(pw_tab, orient="vertical", command=self._pw_tree.yview)
        self._pw_tree.configure(yscrollcommand=pw_scroll.set)
        self._pw_tree.pack(side="left", fill="both", expand=True)
        pw_scroll.pack(side="right", fill="y")

        # ── Tab 4: Settings ──────────────────────────────────────────
        settings_tab = ttk.Frame(notebook, padding=16)
        notebook.add(settings_tab, text="  Settings  ")

        ttk.Label(settings_tab, text="Settings", style="CardHeader.TLabel").pack(anchor="w", pady=(0, 4))
        ttk.Label(settings_tab, text="Configure auto-purge schedule for activity logs", style="TabInfo.TLabel").pack(anchor="w", pady=(0, 16))

        # Purge schedule card
        purge_card = ttk.LabelFrame(settings_tab, text="  Auto-Purge Schedule  ", padding=16)
        purge_card.pack(fill="x", pady=(0, 16))

        ttk.Label(purge_card, text="Automatically delete activity log entries older than:", font=("Helvetica", 11)).pack(anchor="w", pady=(0, 10))

        self._purge_var = tk.StringVar(value=get_purge_schedule())
        purge_grid = ttk.Frame(purge_card)
        purge_grid.pack(anchor="w", padx=8)
        for i, (label, key) in enumerate([("Daily (1 day)", "daily"), ("Weekly (7 days)", "weekly"), ("Bi-weekly (14 days)", "biweekly"), ("Monthly (30 days)", "monthly"), ("Never", "never")]):
            ttk.Radiobutton(purge_grid, text=label, variable=self._purge_var, value=key,
                            command=self._on_purge_change).grid(row=i, column=0, sticky="w", pady=4, padx=4)

        # Manual purge card
        manual_card = ttk.LabelFrame(settings_tab, text="  Manual Actions  ", padding=16)
        manual_card.pack(fill="x", pady=(0, 16))

        purge_btn_row = ttk.Frame(manual_card)
        purge_btn_row.pack(fill="x")
        ttk.Button(purge_btn_row, text="🗑  Purge Old Logs Now", command=self._purge_now).pack(side="left", padx=(0, 12))
        self._purge_status = ttk.Label(purge_btn_row, text="", style="TabInfo.TLabel")
        self._purge_status.pack(side="left")

        # OS info footer
        sys_info = f"{platform.system()} {platform.release()} • Python {platform.python_version()}"
        ttk.Label(container, text=sys_info, style="Status.TLabel", foreground="gray").pack(anchor="e", pady=(4, 0))

    # ── Helpers ──────────────────────────────────────────────────────

    def _log_msg(self, msg: str) -> None:
        from datetime import datetime
        now = datetime.now().strftime("%H:%M:%S")
        tag = "info"
        if "✅" in msg or "Success" in msg:
            tag = "success"
        elif "❌" in msg or "Error" in msg:
            tag = "error"
        self._log_tree.insert("", "end", values=(now, msg), tags=(tag,))
        # Auto-scroll to latest
        children = self._log_tree.get_children()
        if children:
            self._log_tree.see(children[-1])

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
        # Clear existing rows
        for item in self._activity_tree.get_children():
            self._activity_tree.delete(item)
        entries = get_activity_log()
        if not entries:
            self._activity_tree.insert("", "end", values=("—", "—", "No activity recorded yet", "—"))
        else:
            for e in reversed(entries):
                action = e.get("action", "?")
                result = e.get("result", "")
                tag = "lock" if action == "Lock" else "unlock"
                if "Error" in result:
                    tag = "error_row"
                self._activity_tree.insert("", "end", values=(
                    e.get("timestamp", "?"),
                    f"🔐 {action}" if action == "Lock" else f"🔓 {action}",
                    e.get("target", "?"),
                    result,
                ), tags=(tag,))

    def _clear_activity_log(self) -> None:
        if messagebox.askyesno("Clear Activity Log", "Delete all activity log entries?"):
            clear_activity_log()
            self._refresh_activity_log()
            self._log_msg("Activity log cleared.")

    # ── Password history helpers ─────────────────────────────────────

    def _refresh_pw_history(self) -> None:
        for item in self._pw_tree.get_children():
            self._pw_tree.delete(item)
        history = get_password_history()
        if not history:
            self._pw_tree.insert("", "end", values=("No password history saved yet", "—", "—"))
        else:
            for path, entries in history.items():
                for e in entries:
                    self._pw_tree.insert("", "end", values=(
                        path,
                        e.get("timestamp", "?"),
                        e.get("password", "?"),
                    ))

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
        self._purge_status.configure(text=f"✓ Schedule saved: {schedule}", foreground="#16a34a")

    def _purge_now(self) -> None:
        removed = auto_purge()
        self._log_msg(f"Purged {removed} old log entries.")
        self._purge_status.configure(text=f"✓ Purged {removed} entries", foreground="#16a34a")
        self._refresh_activity_log()


# ── Entry point ──────────────────────────────────────────────────────

def launch_gui() -> None:
    auto_purge()  # purge old logs based on saved schedule
    app = PassLockApp()
    app.mainloop()


if __name__ == "__main__":
    launch_gui()
