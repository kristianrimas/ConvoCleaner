"""
NUL File Cleaner
A GUI tool to find and delete stray 'nul' files created by Claude Code on Windows.
"""

import ctypes
import os
import subprocess
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk


class NulCleanerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("NUL File Cleaner")
        self.root.geometry("900x560")
        self.root.minsize(700, 400)

        # Default scan roots
        self.scan_roots = [
            Path("C:\\_Projects"),
            Path.home(),
        ]

        self.found_files = {}  # iid -> Path

        self.setup_ui()
        self.scan()

    def setup_ui(self):
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Top bar
        top_frame = ttk.Frame(main_frame)
        top_frame.pack(fill=tk.X, pady=(0, 10))

        self.stats_label = ttk.Label(top_frame, text="Scanning...", font=("Segoe UI", 10))
        self.stats_label.pack(side=tk.LEFT)

        ttk.Button(top_frame, text="Rescan", command=self.scan).pack(side=tk.RIGHT, padx=(5, 0))
        ttk.Button(top_frame, text="Add Folder...", command=self.add_folder).pack(side=tk.RIGHT)

        # Scan roots display
        roots_frame = ttk.Frame(main_frame)
        roots_frame.pack(fill=tk.X, pady=(0, 10))

        ttk.Label(roots_frame, text="Scan roots:").pack(side=tk.LEFT, padx=(0, 5))
        self.roots_label = ttk.Label(roots_frame, text="", foreground="gray")
        self.roots_label.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self._update_roots_label()

        # Treeview
        tree_frame = ttk.Frame(main_frame)
        tree_frame.pack(fill=tk.BOTH, expand=True)

        columns = ("directory", "size", "modified")
        self.tree = ttk.Treeview(tree_frame, columns=columns, selectmode="extended", show="headings")

        self.tree.heading("directory", text="File Path", anchor=tk.W)
        self.tree.heading("size", text="Size", anchor=tk.E)
        self.tree.heading("modified", text="Modified", anchor=tk.W)

        self.tree.column("directory", width=580, minwidth=300)
        self.tree.column("size", width=80, minwidth=60, anchor=tk.E)
        self.tree.column("modified", width=150, minwidth=120)

        vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        hsb = ttk.Scrollbar(tree_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        tree_frame.grid_rowconfigure(0, weight=1)
        tree_frame.grid_columnconfigure(0, weight=1)

        # Buttons
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill=tk.X, pady=(10, 0))

        ttk.Button(btn_frame, text="Select All", command=self.select_all).pack(side=tk.LEFT, padx=(0, 5))

        self.delete_btn = ttk.Button(btn_frame, text="Delete Selected", command=self.delete_selected)
        self.delete_btn.pack(side=tk.RIGHT)

        # Status bar
        self.status_var = tk.StringVar(value="Ready")
        ttk.Label(main_frame, textvariable=self.status_var, relief=tk.SUNKEN, anchor=tk.W).pack(
            fill=tk.X, pady=(10, 0)
        )

        self.tree.bind("<<TreeviewSelect>>", self.on_select)

        style = ttk.Style()
        style.configure("Treeview", rowheight=25)

    def _update_roots_label(self):
        self.roots_label.config(text="  |  ".join(str(r) for r in self.scan_roots))

    def add_folder(self):
        folder = filedialog.askdirectory(title="Select folder to scan for 'nul' files")
        if folder:
            path = Path(folder)
            if path not in self.scan_roots:
                self.scan_roots.append(path)
                self._update_roots_label()
                self.scan()

    # ── Scanning ─────────────────────────────────────────────────

    def scan(self):
        self.tree.delete(*self.tree.get_children())
        self.found_files.clear()
        self.stats_label.config(text="Scanning...")
        self.status_var.set("Scanning...")
        self.root.update_idletasks()

        total_size = 0
        idx = 0

        for scan_root in self.scan_roots:
            if not scan_root.exists():
                continue

            for dirpath, dirnames, filenames in os.walk(scan_root):
                # Skip .git internals, node_modules, __pycache__, etc.
                dirnames[:] = [
                    d for d in dirnames
                    if d not in (".git", "node_modules", "__pycache__", ".venv", "venv", ".tox")
                ]

                for fname in filenames:
                    if fname.lower() == "nul":
                        full_path = Path(dirpath) / fname
                        try:
                            stat = full_path.stat()
                            size = stat.st_size
                            mtime = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
                        except OSError:
                            size = 0
                            mtime = "?"

                        iid = f"nul_{idx}"
                        self.found_files[iid] = full_path

                        self.tree.insert(
                            "", tk.END, iid=iid,
                            values=(str(full_path), self.format_size(size), mtime),
                        )
                        total_size += size
                        idx += 1

        count = len(self.found_files)
        self.stats_label.config(text=f"{count} nul file(s) found | {self.format_size(total_size)} total")
        self.status_var.set(f"Scan complete: {count} nul file(s) found")

    # ── Selection ────────────────────────────────────────────────

    def select_all(self):
        all_items = self.tree.get_children()
        self.tree.selection_set(all_items)

    def on_select(self, event):
        count = len(self.tree.selection())
        if count > 0:
            self.status_var.set(f"{count} file(s) selected")
        else:
            self.status_var.set("Ready")

    # ── Deletion ─────────────────────────────────────────────────

    def delete_selected(self):
        selected = self.tree.selection()
        if not selected:
            messagebox.showinfo("Info", "Please select files to delete")
            return

        confirm = messagebox.askyesno(
            "Confirm Deletion",
            f"Delete {len(selected)} nul file(s)?\n\nThis cannot be undone!",
        )
        if not confirm:
            return

        deleted = 0
        errors = []

        for iid in selected:
            path = self.found_files.get(iid)
            if not path:
                continue
            try:
                success = self._delete_reserved_file(path)
                if success:
                    deleted += 1
                else:
                    errors.append(f"Could not delete: {path}")
            except Exception as e:
                errors.append(f"{path.name} in {path.parent}: {e}")

        if errors:
            messagebox.showwarning(
                "Partial Success",
                f"Deleted {deleted} file(s)\n\nErrors:\n" + "\n".join(errors[:10]),
            )
        else:
            messagebox.showinfo("Success", f"Deleted {deleted} nul file(s)")

        self.scan()

    # ── Reserved File Deletion ───────────────────────────────────

    def _delete_reserved_file(self, path):
        """Delete a file with a Windows reserved name (nul, con, prn, aux, etc.)
        using the \\\\?\\ UNC prefix to bypass device name resolution."""
        # Build the \\?\ prefixed path for Windows API
        abs_path = str(path.resolve())
        if not abs_path.startswith("\\\\?\\"):
            unc_path = f"\\\\?\\{abs_path}"
        else:
            unc_path = abs_path

        # Try Python's os.remove with UNC path first
        try:
            os.remove(unc_path)
            return True
        except OSError:
            pass

        # Fallback: use del command with the \\?\ path
        try:
            result = subprocess.run(
                ["cmd", "/c", "del", "/f", "/q", unc_path],
                capture_output=True, timeout=10,
            )
            if result.returncode == 0:
                return True
        except Exception:
            pass

        # Fallback: use Windows API DeleteFileW directly
        try:
            kernel32 = ctypes.windll.kernel32
            if kernel32.DeleteFileW(unc_path):
                return True
        except Exception:
            pass

        return False

    # ── Utilities ────────────────────────────────────────────────

    def format_size(self, size):
        for unit in ["B", "KB", "MB", "GB"]:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} TB"


def main():
    root = tk.Tk()
    try:
        root.iconbitmap(default="")
    except Exception:
        pass
    app = NulCleanerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
