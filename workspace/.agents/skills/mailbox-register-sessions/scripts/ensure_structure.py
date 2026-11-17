#!/usr/bin/env python3
"""Create missing mailbox directories, preserving all registration and task files."""
import argparse
import json
import re
from pathlib import Path


def ensure(root):
    root = root.expanduser().resolve()
    for filename in ("AGENTS.md", "README.md", "projects.json"):
        if not (root / filename).is_file():
            raise ValueError(f"Missing required mailbox file: {root / filename}")
    projects = json.loads((root / "projects.json").read_text())["projects"]
    ids = [p["id"] for p in projects]
    if len(ids) != len(set(ids)) or not all(re.fullmatch(r"[a-z0-9][a-z0-9_-]*", x) for x in ids):
        raise ValueError("Project IDs must be unique safe directory names")
    targets = [root / name for name in ("sessions", "projects", "epics", "discovery", "templates")]
    targets += [root / kind / key for kind in ("inbox", "outbox", "archive", "tasks") for key in ids]
    targets += [root / kind / "orchestrator" for kind in ("inbox", "outbox", "archive")]
    for path in targets:
        if not path.resolve().is_relative_to(root):
            raise ValueError(f"Directory escapes mailbox root: {path}")
        if path.exists() and not path.is_dir():
            raise ValueError(f"Expected a directory: {path}")
    created = []
    for path in targets:
        if not path.exists():
            path.mkdir(parents=True, exist_ok=True)
            created.append(str(path.relative_to(root)))
    return {"root": str(root), "projects": ids, "created_directories": created}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.home() / "harness-mailbox")
    args = parser.parse_args()
    print(json.dumps(ensure(args.root), indent=2))
