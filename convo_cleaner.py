"""
Conversation Manager (Claude + Codex)
A GUI tool to view and delete conversations from Claude Code and Codex.
"""

import hashlib
import json
import shutil
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import messagebox, ttk


class ConvoCleanerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Conversation Manager (Claude + Codex)")
        self.root.geometry("1200x720")
        self.root.minsize(980, 520)

        # Paths
        self.claude_projects_path = Path.home() / ".claude" / "projects"
        self.codex_sessions_path = Path.home() / ".codex" / "sessions"
        self.codex_archived_path = Path.home() / ".codex" / "archived_sessions"

        # Data storage
        self.groups_data = {}
        self.session_lookup = {}

        self.setup_ui()
        self.load_all()

    def setup_ui(self):
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Top bar
        top_frame = ttk.Frame(main_frame)
        top_frame.pack(fill=tk.X, pady=(0, 10))

        self.stats_label = ttk.Label(top_frame, text="Loading...", font=("Segoe UI", 10))
        self.stats_label.pack(side=tk.LEFT)

        ttk.Button(top_frame, text="Refresh", command=self.load_all).pack(side=tk.RIGHT)

        # Search
        search_frame = ttk.Frame(main_frame)
        search_frame.pack(fill=tk.X, pady=(0, 10))

        ttk.Label(search_frame, text="Search:").pack(side=tk.LEFT, padx=(0, 5))
        self.search_var = tk.StringVar()
        self.search_var.trace("w", lambda *a: self.filter_tree())
        ttk.Entry(search_frame, textvariable=self.search_var, width=44).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(search_frame, text="Clear", command=lambda: self.search_var.set("")).pack(side=tk.LEFT)

        # Treeview
        tree_frame = ttk.Frame(main_frame)
        tree_frame.pack(fill=tk.BOTH, expand=True)

        columns = ("summary", "msgs", "created", "modified", "branch", "cwd", "size")
        self.tree = ttk.Treeview(tree_frame, columns=columns, selectmode="extended")

        self.tree.heading("#0", text="Project / Session", anchor=tk.W)
        self.tree.heading("summary", text="Summary", anchor=tk.W)
        self.tree.heading("msgs", text="Msgs", anchor=tk.CENTER)
        self.tree.heading("created", text="Created", anchor=tk.W)
        self.tree.heading("modified", text="Modified", anchor=tk.W)
        self.tree.heading("branch", text="Branch", anchor=tk.W)
        self.tree.heading("cwd", text="CWD", anchor=tk.W)
        self.tree.heading("size", text="Size", anchor=tk.E)

        self.tree.column("#0", width=250, minwidth=180)
        self.tree.column("summary", width=280, minwidth=180)
        self.tree.column("msgs", width=50, minwidth=40)
        self.tree.column("created", width=90, minwidth=80)
        self.tree.column("modified", width=90, minwidth=80)
        self.tree.column("branch", width=80, minwidth=60)
        self.tree.column("cwd", width=200, minwidth=100)
        self.tree.column("size", width=70, minwidth=50)

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

        ttk.Button(btn_frame, text="Expand All", command=self.expand_all).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(btn_frame, text="Collapse All", command=self.collapse_all).pack(side=tk.LEFT, padx=(0, 5))

        self.delete_btn = ttk.Button(btn_frame, text="Delete Selected", command=self.delete_selected)
        self.delete_btn.pack(side=tk.RIGHT)

        ttk.Button(btn_frame, text="Select All Sessions", command=self.select_all_sessions).pack(
            side=tk.RIGHT, padx=(0, 10)
        )

        # Status bar
        self.status_var = tk.StringVar(value="Ready")
        ttk.Label(main_frame, textvariable=self.status_var, relief=tk.SUNKEN, anchor=tk.W).pack(
            fill=tk.X, pady=(10, 0)
        )

        # Bindings
        self.tree.bind("<ButtonRelease-1>", self.on_click)
        self.tree.bind("<<TreeviewSelect>>", self.on_select)

        style = ttk.Style()
        style.configure("Treeview", rowheight=25)

    # ── Data Loading ──────────────────────────────────────────────

    def load_all(self):
        self.tree.delete(*self.tree.get_children())
        self.groups_data = {}
        self.session_lookup = {}

        claude_sessions, claude_size = self._load_claude_sessions()
        codex_sessions, codex_size = self._load_codex_sessions()

        total_sessions = claude_sessions + codex_sessions
        total_size = claude_size + codex_size
        group_count = len(self.groups_data)

        self.stats_label.config(
            text=f"{group_count} groups | {total_sessions} sessions | {self.format_size(total_size)} total"
        )
        self.status_var.set(f"Loaded {total_sessions} sessions from {group_count} groups")

    def _load_claude_sessions(self):
        if not self.claude_projects_path.exists():
            return 0, 0

        total_sessions = 0
        total_size = 0

        for project_folder in sorted(self.claude_projects_path.iterdir()):
            if not project_folder.is_dir():
                continue

            sessions_index_path = project_folder / "sessions-index.json"
            index_data = {}
            indexed_sessions = {}

            if sessions_index_path.exists():
                try:
                    with open(sessions_index_path, "r", encoding="utf-8") as f:
                        index_data = json.load(f)
                    for entry in index_data.get("entries", []):
                        indexed_sessions[entry.get("sessionId")] = entry
                except (json.JSONDecodeError, IOError):
                    pass

            original_path = index_data.get("originalPath", self._decode_folder_name(project_folder.name))
            jsonl_files = list(project_folder.rglob("*.jsonl"))

            if not jsonl_files:
                continue

            group_iid = self._make_iid("grp", f"claude:{project_folder.name}")
            display = f"[Claude] {self._shorten_path(original_path)} ({len(jsonl_files)})"

            self.groups_data[group_iid] = {
                "source": "claude",
                "project_path": project_folder,
                "index_path": sessions_index_path,
            }

            group_node = self.tree.insert("", tk.END, iid=group_iid, text=display, open=False, tags=("group",))

            for jsonl_path in sorted(jsonl_files, key=lambda p: p.stat().st_mtime, reverse=True):
                session_filename = jsonl_path.stem
                rel_path = jsonl_path.relative_to(project_folder)
                session_key = str(rel_path).replace("\\", "/").replace(".jsonl", "")
                safe_id = session_key.replace("/", "_").replace("\\", "_")

                if session_filename in indexed_sessions:
                    entry = indexed_sessions[session_filename]
                    summary = entry.get("summary", "No summary")[:80]
                    msg_count = entry.get("messageCount", 0)
                    created = self._format_date(entry.get("created", ""))
                    modified = self._format_date(entry.get("modified", ""))
                    branch = entry.get("gitBranch", "")
                else:
                    si = self._parse_claude_session(jsonl_path)
                    summary = si.get("summary", "")[:80]
                    msg_count = si.get("message_count", 0)
                    created = self._format_date(si.get("created", ""))
                    modified = self._format_date(si.get("modified", ""))
                    branch = si.get("branch", "")

                size = self._get_file_size(jsonl_path)
                total_size += jsonl_path.stat().st_size if jsonl_path.exists() else 0

                display_name = session_filename[:12] + "..."
                if "agent-" in session_filename:
                    display_name = f"[agent] {session_filename[6:18]}..."

                session_iid = self._make_iid("sess", f"claude:{project_folder.name}:{safe_id}")

                self.session_lookup[session_iid] = {
                    "source": "claude",
                    "jsonl_path": jsonl_path,
                    "project_folder_name": project_folder.name,
                    "safe_id": safe_id,
                    "session_filename": session_filename,
                    "group_iid": group_iid,
                }

                self.tree.insert(
                    group_node, tk.END, iid=session_iid, text=display_name,
                    values=(summary, msg_count, created, modified, branch, "", size),
                    tags=("session",),
                )
                total_sessions += 1

        return total_sessions, total_size

    def _load_codex_sessions(self):
        total_sessions = 0
        total_size = 0

        all_entries = []
        if self.codex_sessions_path.exists():
            all_entries.extend(self._collect_codex_entries(self.codex_sessions_path, "active", "sessions"))
        if self.codex_archived_path.exists():
            all_entries.extend(self._collect_codex_entries(self.codex_archived_path, "archived", "archived_sessions"))

        if not all_entries:
            return 0, 0

        grouped = {}
        for entry in all_entries:
            gk = entry["group_key"]
            if gk not in grouped:
                grouped[gk] = {
                    "group_label": entry["group_label"],
                    "storage": entry["storage"],
                    "root_path": entry["root_path"],
                    "entries": [],
                }
            grouped[gk]["entries"].append(entry)

        sorted_groups = sorted(
            grouped.items(),
            key=lambda item: (0 if item[1]["storage"] == "active" else 1, item[1]["group_label"]),
        )

        for group_key, group_info in sorted_groups:
            entries = sorted(group_info["entries"], key=lambda e: e["path"].stat().st_mtime, reverse=True)
            group_iid = self._make_iid("grp", f"codex:{group_key}")

            self.groups_data[group_iid] = {
                "source": "codex",
                "root_path": group_info["root_path"],
            }

            display = f"[Codex] {group_info['group_label']} ({len(entries)})"
            group_node = self.tree.insert("", tk.END, iid=group_iid, text=display, open=False, tags=("group",))

            for entry in entries:
                jsonl_path = entry["path"]
                session_rel = entry["session_rel"]
                si = self._parse_codex_session(jsonl_path)

                size = self._get_file_size(jsonl_path)
                total_size += jsonl_path.stat().st_size if jsonl_path.exists() else 0

                session_iid = self._make_iid("sess", f"codex:{jsonl_path}")
                display_name = Path(session_rel).stem
                if len(display_name) > 56:
                    display_name = display_name[:53] + "..."

                self.session_lookup[session_iid] = {
                    "source": "codex",
                    "jsonl_path": jsonl_path,
                    "root_path": entry["root_path"],
                    "group_iid": group_iid,
                }

                self.tree.insert(
                    group_node, tk.END, iid=session_iid, text=display_name,
                    values=(
                        si.get("summary", ""),
                        si.get("message_count", 0),
                        self._format_date(si.get("created", "")),
                        self._format_date(si.get("modified", "")),
                        "",
                        self._shorten_path(si.get("cwd", "")),
                        size,
                    ),
                    tags=("session",),
                )
                total_sessions += 1

        return total_sessions, total_size

    def _collect_codex_entries(self, root_path, storage, label_prefix):
        entries = []
        for jsonl_path in root_path.rglob("*.jsonl"):
            rel_path = jsonl_path.relative_to(root_path)
            parent_rel = str(rel_path.parent).replace("\\", "/")
            if parent_rel == ".":
                parent_rel = ""
            group_key = f"{storage}:{parent_rel}"
            group_label = label_prefix if not parent_rel else f"{label_prefix}/{parent_rel}"
            entries.append({
                "group_key": group_key,
                "group_label": group_label,
                "storage": storage,
                "root_path": root_path,
                "session_rel": str(rel_path).replace("\\", "/"),
                "path": jsonl_path,
            })
        return entries

    # ── Claude Session Parsing ────────────────────────────────────

    def _parse_claude_session(self, jsonl_path):
        info = {"summary": "", "message_count": 0, "created": "", "modified": "", "branch": ""}
        try:
            first_user_message = None
            timestamps = []
            message_count = 0
            branch = ""

            with open(jsonl_path, "r", encoding="utf-8") as f:
                for line in f:
                    if not line.strip():
                        continue
                    try:
                        entry = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    if entry.get("type") == "user":
                        message_count += 1
                        if first_user_message is None:
                            msg = entry.get("message", {})
                            content = msg.get("content", "")
                            if isinstance(content, str):
                                first_user_message = content
                            elif isinstance(content, list):
                                for item in content:
                                    if isinstance(item, dict) and item.get("type") == "text":
                                        first_user_message = item.get("text", "")
                                        break
                                    elif isinstance(item, str):
                                        first_user_message = item
                                        break

                    if not branch and entry.get("gitBranch"):
                        branch = entry.get("gitBranch")

                    if entry.get("timestamp"):
                        timestamps.append(entry.get("timestamp"))

            if first_user_message:
                info["summary"] = first_user_message.split("\n")[0][:100]
            info["message_count"] = message_count
            info["branch"] = branch

            if timestamps:
                timestamps.sort()
                info["created"] = timestamps[0]
                info["modified"] = timestamps[-1]

        except Exception as e:
            print(f"Error parsing {jsonl_path}: {e}")

        return info

    def _decode_folder_name(self, folder_name):
        path = folder_name
        if path.startswith("C--") or path.startswith("c--"):
            path = "C:\\" + path[3:]
        path = path.replace("-", "\\")
        return path

    # ── Codex Session Parsing ─────────────────────────────────────

    def _parse_codex_session(self, jsonl_path):
        info = {"summary": "", "message_count": 0, "created": "", "modified": "", "cwd": ""}
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

                    ts = entry.get("timestamp")
                    if ts:
                        timestamps.append(ts)

                    entry_type = entry.get("type")

                    if entry_type == "session_meta":
                        payload = entry.get("payload") or {}
                        created = payload.get("timestamp", "")
                        cwd = payload.get("cwd", "")
                        if created and not info["created"]:
                            info["created"] = created
                        if cwd and not info["cwd"]:
                            info["cwd"] = cwd

                    if entry_type == "response_item":
                        payload = entry.get("payload") or {}
                        if payload.get("role") == "user":
                            raw = self._extract_codex_text(payload.get("content"))
                            normalized = self._normalize_codex_text(raw)
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

    def _extract_codex_text(self, content):
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

    def _normalize_codex_text(self, text):
        if not text or not text.strip():
            return ""
        text = text.strip()
        lower = text.lower()
        if lower.startswith("# agents.md instructions"):
            return ""
        if lower.startswith("<environment_context>"):
            return ""
        if lower.startswith("<skill>"):
            return ""
        if lower.startswith("<instructions>"):
            return ""
        if lower.startswith('{"type":"input_image"'):
            return "[image input]"
        if "data:image/" in lower:
            return "[image input]"
        for marker in ("## my request for codex:", "## my request for claude:"):
            idx = lower.find(marker)
            if idx != -1:
                extracted = self._first_meaningful_line(text[idx + len(marker):])
                if extracted:
                    return extracted
        return self._first_meaningful_line(text)

    def _first_meaningful_line(self, text):
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if not lines:
            return ""
        skip_prefixes = (
            "# agents.md instructions", "# context from my ide setup",
            "## active file:", "## open tabs:", "## my request for codex:",
            "## my request for claude:", "<environment_context", "</environment_context",
            "<skill", "</skill", "<instructions", "</instructions",
            "---", "## skills", "- skill-",
        )
        for line in lines:
            ll = line.lower()
            if any(ll.startswith(p) for p in skip_prefixes):
                continue
            if line.startswith("<") and line.endswith(">"):
                continue
            return line[:200]
        return lines[0][:200]

    # ── Tree Interaction ──────────────────────────────────────────

    def on_click(self, event):
        item = self.tree.identify_row(event.y)
        if item and item.startswith("grp_"):
            self.tree.after(10, self._select_group_children, item)

    def _select_group_children(self, group_id):
        children = list(self.tree.get_children(group_id))
        if children:
            self.tree.selection_set(children + [group_id])

    def on_select(self, event):
        selected = self.tree.selection()
        session_count = sum(1 for item in selected if item.startswith("sess_"))
        if session_count > 0:
            self.status_var.set(f"{session_count} session(s) selected")
        else:
            self.status_var.set("Ready")

    def select_all_sessions(self):
        selected = self.tree.selection()
        selected_groups = [item for item in selected if item.startswith("grp_")]

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

    def expand_all(self):
        for item in self.tree.get_children():
            self.tree.item(item, open=True)

    def collapse_all(self):
        for item in self.tree.get_children():
            self.tree.item(item, open=False)

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

    # ── Deletion ──────────────────────────────────────────────────

    def delete_selected(self):
        selected = self.tree.selection()
        sessions_to_delete = [item for item in selected if item.startswith("sess_")]

        if not sessions_to_delete:
            messagebox.showinfo("Info", "Please select sessions to delete (not group folders)")
            return

        confirm = messagebox.askyesno(
            "Confirm Deletion",
            f"Are you sure you want to delete {len(sessions_to_delete)} session(s)?\n\n"
            "This will delete selected conversation files.\n"
            "This action cannot be undone!",
        )
        if not confirm:
            return

        deleted_count = 0
        errors = []
        removed_dirs = set()

        # Track Claude deletions by project for index updates
        claude_by_project = {}

        for item_id in sessions_to_delete:
            info = self.session_lookup.get(item_id)
            if not info:
                errors.append(f"Session data not found: {item_id}")
                continue

            source = info["source"]
            jsonl_path = info["jsonl_path"]

            try:
                if not jsonl_path.exists():
                    if any(jsonl_path.is_relative_to(d) for d in removed_dirs):
                        deleted_count += 1
                    else:
                        errors.append(f"File not found: {jsonl_path.name}")
                    continue

                if source == "claude":
                    jsonl_path.unlink()
                    safe_id = info["safe_id"]
                    if "/" not in safe_id and "_subagents_" not in safe_id:
                        folder = jsonl_path.parent / jsonl_path.stem
                        if folder.exists() and folder.is_dir():
                            removed_dirs.add(folder)
                            shutil.rmtree(folder)
                    proj_name = info["project_folder_name"]
                    if proj_name not in claude_by_project:
                        claude_by_project[proj_name] = []
                    claude_by_project[proj_name].append(info["session_filename"])

                elif source == "codex":
                    jsonl_path.unlink()
                    root_path = info.get("root_path")
                    if root_path and root_path.exists():
                        self._cleanup_empty_dirs(jsonl_path.parent, root_path)

                deleted_count += 1

            except Exception as e:
                errors.append(f"Failed to delete {jsonl_path.name}: {e}")

        # Update Claude session indexes
        for proj_name, deleted_filenames in claude_by_project.items():
            for gdata in self.groups_data.values():
                if (
                    gdata.get("source") == "claude"
                    and gdata.get("project_path")
                    and gdata["project_path"].name == proj_name
                ):
                    index_path = gdata.get("index_path")
                    if index_path and index_path.exists():
                        try:
                            with open(index_path, "r", encoding="utf-8") as f:
                                idx = json.load(f)
                            if idx.get("entries"):
                                idx["entries"] = [
                                    e for e in idx["entries"] if e.get("sessionId") not in deleted_filenames
                                ]
                                with open(index_path, "w", encoding="utf-8") as f:
                                    json.dump(idx, f, indent=2)
                        except Exception as e:
                            errors.append(f"Failed to update index for {proj_name}: {e}")
                    break

        if errors:
            messagebox.showwarning(
                "Partial Success",
                f"Deleted {deleted_count} session(s)\n\nErrors:\n" + "\n".join(errors[:5]),
            )
        else:
            messagebox.showinfo("Success", f"Successfully deleted {deleted_count} session(s)")

        self.load_all()

    def _cleanup_empty_dirs(self, start_dir, stop_dir):
        current = start_dir
        while current != stop_dir:
            try:
                current.relative_to(stop_dir)
            except ValueError:
                break
            try:
                current.rmdir()
            except OSError:
                break
            current = current.parent

    # ── Utilities ─────────────────────────────────────────────────

    def _make_iid(self, prefix, key):
        digest = hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]
        return f"{prefix}_{digest}"

    def _shorten_path(self, path):
        if not path:
            return ""
        try:
            parts = Path(path).parts
        except Exception:
            return str(path)
        if len(parts) > 4:
            return f".../{'/'.join(parts[-3:])}"
        if len(parts) > 3:
            return f".../{'/'.join(parts[-2:])}"
        return str(path)

    def _format_date(self, date_str):
        if not date_str:
            return ""
        try:
            dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            return dt.strftime("%Y-%m-%d")
        except (ValueError, AttributeError):
            return date_str[:10] if len(date_str) >= 10 else date_str

    def _get_file_size(self, path):
        if not path.exists():
            return "N/A"
        return self.format_size(path.stat().st_size)

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
    app = ConvoCleanerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
