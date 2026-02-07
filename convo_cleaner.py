"""
Claude Code Conversation Manager
A GUI tool to view and delete Claude Code conversations across all projects.
"""

import os
import json
import shutil
import tkinter as tk
from tkinter import ttk, messagebox
from datetime import datetime
from pathlib import Path


class ConvoCleanerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Claude Code Conversation Manager")
        self.root.geometry("1100x700")
        self.root.minsize(900, 500)

        # Claude projects path
        self.claude_projects_path = Path.home() / ".claude" / "projects"

        # Data storage
        self.projects_data = {}
        self.selected_items = set()

        self.setup_ui()
        self.load_all_projects()

    def setup_ui(self):
        # Main container
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Top bar with stats and refresh
        top_frame = ttk.Frame(main_frame)
        top_frame.pack(fill=tk.X, pady=(0, 10))

        self.stats_label = ttk.Label(top_frame, text="Loading...", font=("Segoe UI", 10))
        self.stats_label.pack(side=tk.LEFT)

        refresh_btn = ttk.Button(top_frame, text="Refresh", command=self.load_all_projects)
        refresh_btn.pack(side=tk.RIGHT)

        # Search frame
        search_frame = ttk.Frame(main_frame)
        search_frame.pack(fill=tk.X, pady=(0, 10))

        ttk.Label(search_frame, text="Search:").pack(side=tk.LEFT, padx=(0, 5))
        self.search_var = tk.StringVar()
        self.search_var.trace("w", lambda *args: self.filter_tree())
        search_entry = ttk.Entry(search_frame, textvariable=self.search_var, width=40)
        search_entry.pack(side=tk.LEFT, padx=(0, 10))

        ttk.Button(search_frame, text="Clear", command=lambda: self.search_var.set("")).pack(side=tk.LEFT)

        # Treeview with scrollbar
        tree_frame = ttk.Frame(main_frame)
        tree_frame.pack(fill=tk.BOTH, expand=True)

        # Columns
        columns = ("summary", "messages", "created", "modified", "branch", "size")
        self.tree = ttk.Treeview(tree_frame, columns=columns, selectmode="extended")

        # Column headings
        self.tree.heading("#0", text="Project / Session ID", anchor=tk.W)
        self.tree.heading("summary", text="Summary", anchor=tk.W)
        self.tree.heading("messages", text="Msgs", anchor=tk.CENTER)
        self.tree.heading("created", text="Created", anchor=tk.W)
        self.tree.heading("modified", text="Modified", anchor=tk.W)
        self.tree.heading("branch", text="Branch", anchor=tk.W)
        self.tree.heading("size", text="Size", anchor=tk.E)

        # Column widths
        self.tree.column("#0", width=220, minwidth=150)
        self.tree.column("summary", width=300, minwidth=200)
        self.tree.column("messages", width=50, minwidth=40)
        self.tree.column("created", width=100, minwidth=80)
        self.tree.column("modified", width=100, minwidth=80)
        self.tree.column("branch", width=80, minwidth=60)
        self.tree.column("size", width=70, minwidth=50)

        # Scrollbars
        vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        hsb = ttk.Scrollbar(tree_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        # Grid layout for tree and scrollbars
        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        tree_frame.grid_rowconfigure(0, weight=1)
        tree_frame.grid_columnconfigure(0, weight=1)

        # Bottom buttons
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill=tk.X, pady=(10, 0))

        ttk.Button(btn_frame, text="Expand All", command=self.expand_all).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(btn_frame, text="Collapse All", command=self.collapse_all).pack(side=tk.LEFT, padx=(0, 5))

        self.delete_btn = ttk.Button(btn_frame, text="Delete Selected", command=self.delete_selected)
        self.delete_btn.pack(side=tk.RIGHT)

        ttk.Button(btn_frame, text="Select All Sessions", command=self.select_all_sessions).pack(side=tk.RIGHT, padx=(0, 10))

        # Status bar
        self.status_var = tk.StringVar(value="Ready")
        status_bar = ttk.Label(main_frame, textvariable=self.status_var, relief=tk.SUNKEN, anchor=tk.W)
        status_bar.pack(fill=tk.X, pady=(10, 0))

        # Bind selection event
        self.tree.bind("<<TreeviewSelect>>", self.on_select)

        # Style configuration
        style = ttk.Style()
        style.configure("Treeview", rowheight=25)

    def load_all_projects(self):
        """Load all projects and their sessions from Claude's data directory."""
        self.tree.delete(*self.tree.get_children())
        self.projects_data = {}

        if not self.claude_projects_path.exists():
            messagebox.showerror("Error", f"Claude projects path not found:\n{self.claude_projects_path}")
            return

        total_sessions = 0
        total_size = 0

        # Iterate through project folders
        for project_folder in sorted(self.claude_projects_path.iterdir()):
            if not project_folder.is_dir():
                continue

            # Try to get original path from index, otherwise decode folder name
            sessions_index_path = project_folder / "sessions-index.json"
            index_data = {}
            indexed_sessions = {}

            if sessions_index_path.exists():
                try:
                    with open(sessions_index_path, 'r', encoding='utf-8') as f:
                        index_data = json.load(f)
                    # Build lookup of indexed sessions
                    for entry in index_data.get("entries", []):
                        indexed_sessions[entry.get("sessionId")] = entry
                except (json.JSONDecodeError, IOError):
                    pass

            original_path = index_data.get("originalPath", self.decode_folder_name(project_folder.name))

            # Find ALL .jsonl files in this project folder AND subfolders
            jsonl_files = list(project_folder.rglob("*.jsonl"))

            if not jsonl_files:
                continue

            # Store project data
            self.projects_data[project_folder.name] = {
                "path": project_folder,
                "original_path": original_path,
                "index_path": sessions_index_path,
                "sessions": {}
            }

            # Create project node
            project_display = self.shorten_path(original_path)
            project_node = self.tree.insert("", tk.END, iid=f"proj_{project_folder.name}",
                                           text=f"{project_display} ({len(jsonl_files)})",
                                           open=False, tags=("project",))

            # Add sessions from .jsonl files
            for jsonl_path in sorted(jsonl_files, key=lambda p: p.stat().st_mtime, reverse=True):
                session_filename = jsonl_path.stem  # filename without extension
                # Use relative path as unique key to handle subfolders
                rel_path = jsonl_path.relative_to(project_folder)
                session_key = str(rel_path).replace("\\", "/").replace(".jsonl", "")

                # Check if we have index data for this session
                if session_filename in indexed_sessions:
                    entry = indexed_sessions[session_filename]
                    summary = entry.get("summary", "No summary")[:80]
                    message_count = entry.get("messageCount", 0)
                    created = self.format_date(entry.get("created", ""))
                    modified = self.format_date(entry.get("modified", ""))
                    branch = entry.get("gitBranch", "")
                else:
                    # Parse the jsonl file to extract metadata
                    session_info = self.parse_session_file(jsonl_path)
                    summary = session_info.get("summary", "")[:80]
                    message_count = session_info.get("message_count", 0)
                    created = self.format_date(session_info.get("created", ""))
                    modified = self.format_date(session_info.get("modified", ""))
                    branch = session_info.get("branch", "")

                # Calculate file size
                size = self.get_file_size(jsonl_path)
                total_size += jsonl_path.stat().st_size if jsonl_path.exists() else 0

                # Use safe ID for keys (replace special chars)
                safe_id = session_key.replace("/", "_").replace("\\", "_")

                # Store session data with safe_id as key
                self.projects_data[project_folder.name]["sessions"][safe_id] = {
                    "jsonl_path": jsonl_path
                }

                # Display name - show if it's a subagent
                display_name = session_filename[:12] + "..."
                if "agent-" in session_filename:
                    display_name = f"[agent] {session_filename[6:18]}..."

                # Insert into tree
                self.tree.insert(project_node, tk.END,
                               iid=f"sess_{project_folder.name}_{safe_id}",
                               text=display_name,
                               values=(summary, message_count, created, modified, branch, size),
                               tags=("session",))
                total_sessions += 1

        # Update stats
        project_count = len(self.projects_data)
        self.stats_label.config(text=f"{project_count} projects | {total_sessions} sessions | {self.format_size(total_size)} total")
        self.status_var.set(f"Loaded {total_sessions} sessions from {project_count} projects")

    def decode_folder_name(self, folder_name):
        """Decode a Claude folder name back to original path."""
        # Claude encodes paths like C:\_Projects\Foo as C---Projects-Foo
        # Reverse: replace leading C- with C:\, then - with \ or /
        path = folder_name
        if path.startswith("C--"):
            path = "C:\\" + path[3:]
        elif path.startswith("c--"):
            path = "C:\\" + path[3:]
        path = path.replace("-", "\\")
        return path

    def parse_session_file(self, jsonl_path):
        """Parse a .jsonl session file to extract metadata."""
        info = {
            "summary": "",
            "message_count": 0,
            "created": "",
            "modified": "",
            "branch": ""
        }

        try:
            first_user_message = None
            timestamps = []
            message_count = 0
            branch = ""

            with open(jsonl_path, 'r', encoding='utf-8') as f:
                for line in f:
                    if not line.strip():
                        continue
                    try:
                        entry = json.loads(line)

                        # Count user messages
                        if entry.get("type") == "user":
                            message_count += 1
                            if first_user_message is None:
                                msg = entry.get("message", {})
                                content = msg.get("content", "")
                                if isinstance(content, str):
                                    first_user_message = content
                                elif isinstance(content, list):
                                    # Handle content array
                                    for item in content:
                                        if isinstance(item, dict) and item.get("type") == "text":
                                            first_user_message = item.get("text", "")
                                            break
                                        elif isinstance(item, str):
                                            first_user_message = item
                                            break

                        # Get branch
                        if not branch and entry.get("gitBranch"):
                            branch = entry.get("gitBranch")

                        # Collect timestamps
                        if entry.get("timestamp"):
                            timestamps.append(entry.get("timestamp"))

                    except json.JSONDecodeError:
                        continue

            # Set summary from first user message
            if first_user_message:
                # Clean up the summary - take first line, limit length
                summary = first_user_message.split('\n')[0][:100]
                info["summary"] = summary

            info["message_count"] = message_count
            info["branch"] = branch

            if timestamps:
                timestamps.sort()
                info["created"] = timestamps[0]
                info["modified"] = timestamps[-1]

        except Exception as e:
            print(f"Error parsing {jsonl_path}: {e}")

        return info

    def shorten_path(self, path):
        """Shorten a path for display."""
        parts = Path(path).parts
        if len(parts) > 3:
            return f".../{'/'.join(parts[-2:])}"
        return path

    def format_date(self, date_str):
        """Format ISO date string to readable format."""
        if not date_str:
            return ""
        try:
            dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            return dt.strftime("%Y-%m-%d")
        except (ValueError, AttributeError):
            return date_str[:10] if len(date_str) >= 10 else date_str

    def get_file_size(self, path):
        """Get file size as human-readable string."""
        if not path.exists():
            return "N/A"
        size = path.stat().st_size
        return self.format_size(size)

    def format_size(self, size):
        """Format bytes to human-readable size."""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} TB"

    def filter_tree(self):
        """Filter tree based on search text."""
        search_text = self.search_var.get().lower()

        for project_id in self.tree.get_children():
            project_visible = False

            for session_id in self.tree.get_children(project_id):
                values = self.tree.item(session_id, "values")
                text = self.tree.item(session_id, "text")

                # Check if search matches summary, session ID, or branch
                match = (search_text in text.lower() or
                        search_text in values[0].lower() or  # summary
                        search_text in values[4].lower())    # branch

                if match or not search_text:
                    project_visible = True

            # Show/hide project based on whether it has matching sessions
            if project_visible or not search_text:
                self.tree.item(project_id, open=bool(search_text))

    def expand_all(self):
        """Expand all project nodes."""
        for item in self.tree.get_children():
            self.tree.item(item, open=True)

    def collapse_all(self):
        """Collapse all project nodes."""
        for item in self.tree.get_children():
            self.tree.item(item, open=False)

    def select_all_sessions(self):
        """Select all session items (not projects)."""
        session_ids = []
        for project_id in self.tree.get_children():
            for session_id in self.tree.get_children(project_id):
                session_ids.append(session_id)
        self.tree.selection_set(session_ids)

    def on_select(self, event):
        """Handle selection change."""
        selected = self.tree.selection()
        session_count = sum(1 for item in selected if item.startswith("sess_"))
        if session_count > 0:
            self.status_var.set(f"{session_count} session(s) selected")
        else:
            self.status_var.set("Ready")

    def delete_selected(self):
        """Delete selected sessions."""
        selected = self.tree.selection()

        # Filter to only sessions (not projects)
        sessions_to_delete = [item for item in selected if item.startswith("sess_")]

        if not sessions_to_delete:
            messagebox.showinfo("Info", "Please select sessions to delete (not project folders)")
            return

        # Confirmation
        confirm = messagebox.askyesno(
            "Confirm Deletion",
            f"Are you sure you want to delete {len(sessions_to_delete)} session(s)?\n\n"
            "This will:\n"
            "- Delete the conversation files (.jsonl)\n"
            "- Delete any associated subagent folders\n"
            "- Update sessions-index.json\n\n"
            "This action cannot be undone!"
        )

        if not confirm:
            return

        # Group deletions by project
        deletions_by_project = {}
        for item_id in sessions_to_delete:
            parts = item_id.split("_", 2)  # sess_projectfolder_sessionid
            project_folder = parts[1]
            session_id = parts[2]

            if project_folder not in deletions_by_project:
                deletions_by_project[project_folder] = []
            deletions_by_project[project_folder].append(session_id)

        # Perform deletions
        deleted_count = 0
        errors = []

        for project_folder, session_ids in deletions_by_project.items():
            project_data = self.projects_data.get(project_folder)
            if not project_data:
                continue

            # Load current index if it exists
            index_data = {}
            index_path = project_data.get("index_path")
            if index_path and index_path.exists():
                try:
                    with open(index_path, 'r', encoding='utf-8') as f:
                        index_data = json.load(f)
                except Exception:
                    pass

            # Delete each session
            for session_id in session_ids:
                session_data = project_data["sessions"].get(session_id, {})
                jsonl_path = session_data.get("jsonl_path")

                if not jsonl_path:
                    errors.append(f"Session data not found: {session_id}")
                    continue

                try:
                    # Delete .jsonl file
                    if jsonl_path.exists():
                        jsonl_path.unlink()

                    # For main sessions (not subagents), delete associated folder if exists
                    if "/" not in session_id and "_subagents_" not in session_id:
                        folder_path = project_data["path"] / jsonl_path.stem
                        if folder_path.exists() and folder_path.is_dir():
                            shutil.rmtree(folder_path)

                    deleted_count += 1
                except Exception as e:
                    errors.append(f"Failed to delete {session_id}: {e}")

            # Update index file if it exists
            if index_data.get("entries") and index_path:
                new_entries = [e for e in index_data["entries"]
                              if e.get("sessionId") not in session_ids]
                index_data["entries"] = new_entries
                try:
                    with open(index_path, 'w', encoding='utf-8') as f:
                        json.dump(index_data, f, indent=2)
                except Exception as e:
                    errors.append(f"Failed to update index for {project_folder}: {e}")

        # Show results
        if errors:
            messagebox.showwarning(
                "Partial Success",
                f"Deleted {deleted_count} session(s)\n\nErrors:\n" + "\n".join(errors[:5])
            )
        else:
            messagebox.showinfo("Success", f"Successfully deleted {deleted_count} session(s)")

        # Refresh the tree
        self.load_all_projects()


def main():
    root = tk.Tk()

    # Set app icon (optional, uses default if not found)
    try:
        root.iconbitmap(default="")
    except:
        pass

    app = ConvoCleanerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
