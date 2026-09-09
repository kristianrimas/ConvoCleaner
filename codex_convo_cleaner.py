"""
Codex Conversation Manager
A GUI tool to view and delete Codex conversations from local session storage.
"""

import hashlib
import json
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import messagebox, ttk


class CodexConvoCleanerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Codex Conversation Manager")
        self.root.geometry("1200x720")
        self.root.minsize(980, 520)

        self.codex_root = Path.home() / ".codex"
        self.codex_sessions_path = self.codex_root / "sessions"
        self.codex_archived_path = self.codex_root / "archived_sessions"

        self.groups_data = {}
        self.session_lookup = {}

        self.setup_ui()
        self.load_all_sessions()

    def setup_ui(self):
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)

        top_frame = ttk.Frame(main_frame)
        top_frame.pack(fill=tk.X, pady=(0, 10))

        self.stats_label = ttk.Label(top_frame, text="Loading...", font=("Segoe UI", 10))
        self.stats_label.pack(side=tk.LEFT)

        refresh_btn = ttk.Button(top_frame, text="Refresh", command=self.load_all_sessions)
        refresh_btn.pack(side=tk.RIGHT)

        search_frame = ttk.Frame(main_frame)
        search_frame.pack(fill=tk.X, pady=(0, 10))

        ttk.Label(search_frame, text="Search:").pack(side=tk.LEFT, padx=(0, 5))
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *args: self.filter_tree())
        search_entry = ttk.Entry(search_frame, textvariable=self.search_var, width=44)
        search_entry.pack(side=tk.LEFT, padx=(0, 10))

        ttk.Button(search_frame, text="Clear", command=lambda: self.search_var.set("")).pack(side=tk.LEFT)

        tree_frame = ttk.Frame(main_frame)
        tree_frame.pack(fill=tk.BOTH, expand=True)

        columns = ("summary", "prompts", "created", "modified", "cwd", "size")
        self.tree = ttk.Treeview(tree_frame, columns=columns, selectmode="extended")

        self.tree.heading("#0", text="Session File", anchor=tk.W)
        self.tree.heading("summary", text="Summary", anchor=tk.W)
        self.tree.heading("prompts", text="Prompts", anchor=tk.CENTER)
        self.tree.heading("created", text="Created", anchor=tk.W)
        self.tree.heading("modified", text="Modified", anchor=tk.W)
        self.tree.heading("cwd", text="CWD", anchor=tk.W)
        self.tree.heading("size", text="Size", anchor=tk.E)

        self.tree.column("#0", width=310, minwidth=220)
        self.tree.column("summary", width=360, minwidth=220)
        self.tree.column("prompts", width=70, minwidth=50, anchor=tk.CENTER)
        self.tree.column("created", width=100, minwidth=90)
        self.tree.column("modified", width=100, minwidth=90)
        self.tree.column("cwd", width=240, minwidth=140)
        self.tree.column("size", width=80, minwidth=60, anchor=tk.E)

        vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        hsb = ttk.Scrollbar(tree_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        tree_frame.grid_rowconfigure(0, weight=1)
        tree_frame.grid_columnconfigure(0, weight=1)

        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill=tk.X, pady=(10, 0))

        ttk.Button(btn_frame, text="Expand All", command=self.expand_all).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(btn_frame, text="Collapse All", command=self.collapse_all).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(btn_frame, text="Select All Sessions", command=self.select_all_sessions).pack(
            side=tk.RIGHT, padx=(0, 10)
        )
        self.delete_btn = ttk.Button(btn_frame, text="Delete Selected", command=self.delete_selected)
        self.delete_btn.pack(side=tk.RIGHT)

        self.status_var = tk.StringVar(value="Ready")
        status_bar = ttk.Label(main_frame, textvariable=self.status_var, relief=tk.SUNKEN, anchor=tk.W)
        status_bar.pack(fill=tk.X, pady=(10, 0))

        self.tree.bind("<ButtonRelease-1>", self.on_click)
        self.tree.bind("<<TreeviewSelect>>", self.on_select)

        style = ttk.Style()
        style.configure("Treeview", rowheight=25)

    def load_all_sessions(self):
        self.tree.delete(*self.tree.get_children())
        self.groups_data = {}
        self.session_lookup = {}

        if not self.codex_sessions_path.exists() and not self.codex_archived_path.exists():
            messagebox.showerror(
                "Error",
                "Codex session paths were not found:\n"
                f"{self.codex_sessions_path}\n"
                f"{self.codex_archived_path}",
            )
            return

        all_entries = []
        if self.codex_sessions_path.exists():
            all_entries.extend(self.collect_session_entries(self.codex_sessions_path, "active", "sessions"))
        if self.codex_archived_path.exists():
            all_entries.extend(self.collect_session_entries(self.codex_archived_path, "archived", "archived_sessions"))

        if not all_entries:
            self.stats_label.config(text="0 groups | 0 sessions | 0.0 B total")
            self.status_var.set("No sessions found")
            return

        grouped = {}
        for entry in all_entries:
            group_key = entry["group_key"]
            if group_key not in grouped:
                grouped[group_key] = {
                    "group_label": entry["group_label"],
                    "storage": entry["storage"],
                    "root_path": entry["root_path"],
                    "entries": [],
                }
            grouped[group_key]["entries"].append(entry)

        total_sessions = 0
        total_size = 0

        sorted_groups = sorted(
            grouped.items(),
            key=lambda item: (0 if item[1]["storage"] == "active" else 1, item[1]["group_label"]),
        )

        for group_key, group_info in sorted_groups:
            group_iid = self.make_group_iid(group_key)
            entries = sorted(group_info["entries"], key=lambda e: e["path"].stat().st_mtime, reverse=True)

            self.groups_data[group_key] = {
                "group_label": group_info["group_label"],
                "storage": group_info["storage"],
                "root_path": group_info["root_path"],
                "sessions": {},
            }

            group_node = self.tree.insert(
                "",
                tk.END,
                iid=group_iid,
                text=f"{group_info['group_label']} ({len(entries)})",
                open=False,
                tags=("group",),
            )

            for entry in entries:
                jsonl_path = entry["path"]
                session_rel = entry["session_rel"]
                session_info = self.parse_session_file(jsonl_path)

                size = self.get_file_size(jsonl_path)
                total_size += jsonl_path.stat().st_size if jsonl_path.exists() else 0

                session_iid = self.make_session_iid(jsonl_path)
                display_name = self.format_session_display_name(session_rel)

                self.groups_data[group_key]["sessions"][session_iid] = {
                    "jsonl_path": jsonl_path,
                    "session_rel": session_rel,
                }
                self.session_lookup[session_iid] = {
                    "jsonl_path": jsonl_path,
                    "root_path": entry["root_path"],
                    "group_key": group_key,
                }

                self.tree.insert(
                    group_node,
                    tk.END,
                    iid=session_iid,
                    text=display_name,
                    values=(
                        session_info.get("summary", ""),
                        session_info.get("message_count", 0),
                        self.format_date(session_info.get("created", "")),
                        self.format_date(session_info.get("modified", "")),
                        self.shorten_path(session_info.get("cwd", "")),
                        size,
                    ),
                    tags=("session",),
                )
                total_sessions += 1

        group_count = len(self.groups_data)
        self.stats_label.config(
            text=f"{group_count} groups | {total_sessions} sessions | {self.format_size(total_size)} total"
        )
        self.status_var.set(f"Loaded {total_sessions} sessions from {group_count} groups")

    def collect_session_entries(self, root_path, storage, label_prefix):
        entries = []
        for jsonl_path in root_path.rglob("*.jsonl"):
            rel_path = jsonl_path.relative_to(root_path)
            parent_rel = str(rel_path.parent).replace("\\", "/")
            if parent_rel == ".":
                parent_rel = ""

            group_key = f"{storage}:{parent_rel}"
            group_label = label_prefix if not parent_rel else f"{label_prefix}/{parent_rel}"
            entries.append(
                {
                    "group_key": group_key,
                    "group_label": group_label,
                    "storage": storage,
                    "root_path": root_path,
                    "session_rel": str(rel_path).replace("\\", "/"),
                    "path": jsonl_path,
                }
            )
        return entries

    def parse_session_file(self, jsonl_path):
        info = {
            "summary": "",
            "message_count": 0,
            "created": "",
            "modified": "",
            "cwd": "",
            "source": "",
            "session_id": "",
        }

        first_prompt = None
        last_prompt = None
        timestamps = []

        try:
            with open(jsonl_path, "r", encoding="utf-8") as f:
                for line in f:
                    if not line.strip():
                        continue

                    try:
                        entry = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    timestamp = entry.get("timestamp")
                    if timestamp:
                        timestamps.append(timestamp)

                    entry_type = entry.get("type")

                    if entry_type == "session_meta":
                        payload = entry.get("payload") or {}
                        session_id = payload.get("id", "")
                        created = payload.get("timestamp", "")
                        cwd = payload.get("cwd", "")
                        source = payload.get("source") or payload.get("originator", "")

                        if session_id:
                            info["session_id"] = session_id
                        if created and not info["created"]:
                            info["created"] = created
                        if cwd and not info["cwd"]:
                            info["cwd"] = cwd
                        if source and not info["source"]:
                            info["source"] = source

                    if entry_type == "response_item":
                        payload = entry.get("payload") or {}
                        if payload.get("role") == "user":
                            raw_text = self.extract_text_from_content(payload.get("content"))
                            normalized = self.normalize_user_text(raw_text)
                            if normalized:
                                info["message_count"] += 1
                                if first_prompt is None:
                                    first_prompt = normalized
                                last_prompt = normalized

            if first_prompt:
                info["summary"] = first_prompt[:120]
            elif last_prompt:
                info["summary"] = last_prompt[:120]
            else:
                info["summary"] = jsonl_path.stem

            if timestamps:
                timestamps.sort()
                if not info["created"]:
                    info["created"] = timestamps[0]
                info["modified"] = timestamps[-1]

        except Exception as e:
            print(f"Error parsing {jsonl_path}: {e}")
            info["summary"] = jsonl_path.stem

        return info

    def extract_text_from_content(self, content):
        if isinstance(content, str):
            return content

        extracted = []

        items = content if isinstance(content, list) else [content]
        for item in items:
            if isinstance(item, str):
                extracted.append(item)
                continue
            if not isinstance(item, dict):
                continue

            item_type = item.get("type")
            if item_type in ("input_text", "text"):
                text = item.get("text", "")
                if isinstance(text, str) and text:
                    extracted.append(text)
            elif item_type in ("input_image", "image", "image_url"):
                extracted.append("[image input]")
            elif isinstance(item.get("text"), str):
                extracted.append(item.get("text"))

        return "\n".join(part for part in extracted if part).strip()

    def normalize_user_text(self, text):
        if not text:
            return ""

        text = text.strip()
        if not text:
            return ""

        lower = text.lower()
        if lower.startswith("# agents.md instructions"):
            return ""
        if lower.startswith("<environment_context>"):
            return ""
        if lower.startswith("<skill>"):
            return ""
        if lower.startswith("<instructions>"):
            return ""
        if lower.startswith("{\"type\":\"input_image\""):
            return "[image input]"
        if "data:image/" in lower:
            return "[image input]"

        for marker in ("## my request for codex:", "## my request for claude:"):
            idx = lower.find(marker)
            if idx != -1:
                extracted = self.first_meaningful_line(text[idx + len(marker) :])
                if extracted:
                    return extracted

        return self.first_meaningful_line(text)

    def first_meaningful_line(self, text):
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if not lines:
            return ""

        for line in lines:
            lower = line.lower()

            if lower.startswith("# agents.md instructions"):
                continue
            if lower.startswith("# context from my ide setup"):
                continue
            if lower.startswith("## active file:"):
                continue
            if lower.startswith("## open tabs:"):
                continue
            if lower.startswith("## my request for codex:"):
                continue
            if lower.startswith("## my request for claude:"):
                continue
            if lower.startswith("<environment_context"):
                continue
            if lower.startswith("</environment_context"):
                continue
            if lower.startswith("<skill"):
                continue
            if lower.startswith("</skill"):
                continue
            if lower.startswith("<instructions"):
                continue
            if lower.startswith("</instructions"):
                continue
            if lower.startswith("---"):
                continue
            if lower.startswith("## skills"):
                continue
            if lower.startswith("- skill-"):
                continue
            if line.startswith("<") and line.endswith(">"):
                continue

            return line[:200]

        return lines[0][:200]

    def make_group_iid(self, group_key):
        digest = hashlib.sha1(group_key.encode("utf-8")).hexdigest()[:16]
        return f"group|{digest}"

    def make_session_iid(self, jsonl_path):
        digest = hashlib.sha1(str(jsonl_path).encode("utf-8")).hexdigest()[:20]
        return f"sess|{digest}"

    def format_session_display_name(self, session_rel):
        stem = Path(session_rel).stem
        return stem if len(stem) <= 56 else f"{stem[:53]}..."

    def shorten_path(self, path):
        if not path:
            return ""
        try:
            parts = Path(path).parts
        except Exception:
            return path
        if len(parts) > 4:
            return f".../{'/'.join(parts[-3:])}"
        return path

    def format_date(self, date_str):
        if not date_str:
            return ""
        try:
            dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            return dt.astimezone().strftime("%Y-%m-%d")
        except (ValueError, AttributeError):
            return date_str[:10] if len(date_str) >= 10 else date_str

    def get_file_size(self, path):
        if not path.exists():
            return "N/A"
        return self.format_size(path.stat().st_size)

    def format_size(self, size):
        for unit in ["B", "KB", "MB", "GB"]:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} TB"

    def filter_tree(self):
        search_text = self.search_var.get().strip().lower()
        for group_id in self.tree.get_children():
            group_has_match = False
            for session_id in self.tree.get_children(group_id):
                values = self.tree.item(session_id, "values")
                text = self.tree.item(session_id, "text")
                haystack = " ".join([str(text)] + [str(v) for v in values]).lower()
                if not search_text or search_text in haystack:
                    group_has_match = True
            self.tree.item(group_id, open=bool(search_text and group_has_match))

    def expand_all(self):
        for item in self.tree.get_children():
            self.tree.item(item, open=True)

    def collapse_all(self):
        for item in self.tree.get_children():
            self.tree.item(item, open=False)

    def select_all_sessions(self):
        """Select all sessions under selected groups, or all if none selected."""
        selected = self.tree.selection()
        selected_groups = [item for item in selected if item.startswith("group|")]

        session_ids = []
        if selected_groups:
            for group_id in selected_groups:
                for session_id in self.tree.get_children(group_id):
                    session_ids.append(session_id)
        else:
            for group_id in self.tree.get_children():
                for session_id in self.tree.get_children(group_id):
                    session_ids.append(session_id)
        self.tree.selection_set(session_ids)

    def on_click(self, event):
        """Handle click - auto-select children when clicking a group folder."""
        item = self.tree.identify_row(event.y)
        if item and item.startswith("group|"):
            self.tree.after(10, self._select_group_children, item)

    def _select_group_children(self, group_id):
        """Select all sessions under a group."""
        children = list(self.tree.get_children(group_id))
        if children:
            self.tree.selection_set(children + [group_id])

    def on_select(self, event):
        """Handle selection change - update status bar."""
        selected = self.tree.selection()
        session_count = sum(1 for item in selected if item.startswith("sess|"))
        if session_count > 0:
            self.status_var.set(f"{session_count} session(s) selected")
        else:
            self.status_var.set("Ready")

    def delete_selected(self):
        selected = self.tree.selection()
        sessions_to_delete = [item for item in selected if item.startswith("sess|")]

        if not sessions_to_delete:
            messagebox.showinfo("Info", "Please select sessions to delete (not group folders)")
            return

        confirm = messagebox.askyesno(
            "Confirm Deletion",
            f"Are you sure you want to delete {len(sessions_to_delete)} session(s)?\n\n"
            "This will:\n"
            "- Delete selected .jsonl conversation files\n"
            "- Remove empty parent folders under sessions/archive roots\n\n"
            "This action cannot be undone!",
        )
        if not confirm:
            return

        deleted_count = 0
        errors = []

        for item_id in sessions_to_delete:
            session_data = self.session_lookup.get(item_id, {})
            jsonl_path = session_data.get("jsonl_path")
            root_path = session_data.get("root_path")

            if not jsonl_path:
                errors.append(f"Session data not found: {item_id}")
                continue

            try:
                if jsonl_path.exists():
                    jsonl_path.unlink()
                    deleted_count += 1
                    if root_path and root_path.exists():
                        self.cleanup_empty_dirs(jsonl_path.parent, root_path)
                else:
                    errors.append(f"File not found: {jsonl_path}")
            except Exception as e:
                errors.append(f"Failed to delete {jsonl_path.name}: {e}")

        if errors:
            messagebox.showwarning(
                "Partial Success",
                f"Deleted {deleted_count} session(s)\n\nErrors:\n" + "\n".join(errors[:5]),
            )
        else:
            messagebox.showinfo("Success", f"Successfully deleted {deleted_count} session(s)")

        self.load_all_sessions()

    def cleanup_empty_dirs(self, start_dir, stop_dir):
        current = start_dir
        while current != stop_dir and self.is_within(current, stop_dir):
            try:
                current.rmdir()
            except OSError:
                break
            current = current.parent

    def is_within(self, path, parent):
        try:
            path.relative_to(parent)
            return True
        except ValueError:
            return False


def main():
    root = tk.Tk()

    try:
        root.iconbitmap(default="")
    except Exception:
        pass

    app = CodexConvoCleanerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
