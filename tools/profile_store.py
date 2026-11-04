"""Read and write profiles on disk.

profiles/<slug>/
  meta.json          name, relationship, target/me sender names, version, timestamps
  style.json         output of style_analyzer.analyze (minus examples)
  persona.md         who they are and how they text, for humans
  examples.jsonl     real (context -> reply) pairs pulled from the chat
  corrections.jsonl  "they'd never say that, they'd say X" fixes you made
  approved.jsonl     generated replies you marked as spot-on
  messages.jsonl     the raw parsed chat (needed to re-learn incrementally)
  history/v<N>.json  (older profiles) the style before each re-learn
  snapshots/NNNN/    a full copy of the files above, taken before every change, so it can be undone
  persona.md         a readable summary of their texting style
"""
from __future__ import annotations

import json
import os
import re
import shutil
from datetime import datetime
from pathlib import Path

from .chat_parser import Message

REPO_ROOT = Path(__file__).resolve().parent.parent
SNAPSHOTS = "snapshots"
MAX_SNAPSHOTS = 20  # the first one (the profile as created) is always kept
# TEXTPRINT_HOME is the same setting from the brief Textprint name; it still works.
PROFILES_DIR = Path(os.environ.get("TEXTBACK_HOME") or os.environ.get("TEXTPRINT_HOME") or REPO_ROOT / "profiles")


def slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug or "contact"


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


class Profile:
    def __init__(self, slug: str, base: Path | None = None):
        self.slug = slugify(slug)
        self.dir = (base or PROFILES_DIR) / self.slug

    # ---- generic helpers -------------------------------------------------
    def exists(self) -> bool:
        return (self.dir / "meta.json").exists()

    def path(self, name: str) -> Path:
        return self.dir / name

    def read_json(self, name: str, default=None):
        p = self.path(name)
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else default

    def write_json(self, name: str, data) -> None:
        self.path(name).parent.mkdir(parents=True, exist_ok=True)
        self.path(name).write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    def read_jsonl(self, name: str) -> list[dict]:
        p = self.path(name)
        if not p.exists():
            return []
        return [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]

    def write_jsonl(self, name: str, rows: list[dict]) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        body = "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows)
        self.path(name).write_text(body, encoding="utf-8")

    def append_jsonl(self, name: str, row: dict) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        with self.path(name).open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")

    # ---- typed accessors -------------------------------------------------
    @property
    def meta(self) -> dict:
        return self.read_json("meta.json", {})

    @property
    def style(self) -> dict:
        return self.read_json("style.json", {})

    @property
    def persona(self) -> str:
        p = self.path("persona.md")
        return p.read_text(encoding="utf-8") if p.exists() else ""

    def examples(self) -> list[dict]:
        return self.read_jsonl("examples.jsonl")

    def corrections(self) -> list[dict]:
        return self.read_jsonl("corrections.jsonl")

    def approved(self) -> list[dict]:
        return self.read_jsonl("approved.jsonl")

    def messages(self) -> list[Message]:
        return [Message.from_dict(d) for d in self.read_jsonl("messages.jsonl")]

    # ---- snapshots: undo and reset ------------------------------------------
    def _state_files(self) -> list[Path]:
        return [f for f in self.dir.iterdir() if f.is_file()]

    def snapshots(self) -> list[dict]:
        root = self.dir / SNAPSHOTS
        if not root.exists():
            return []
        out = []
        for d in sorted(p for p in root.iterdir() if p.is_dir()):
            info = json.loads((d / "_snapshot.json").read_text(encoding="utf-8")) if (d / "_snapshot.json").exists() else {}
            out.append({"id": d.name, "path": d, **info})
        return out

    def snapshot(self, label: str) -> None:
        """Copy the profile's files before a change, so `undo` can put them back."""
        if not self.exists():
            return
        existing = self.snapshots()
        n = int(existing[-1]["id"]) + 1 if existing else 1
        dest = self.dir / SNAPSHOTS / f"{n:04d}"
        dest.mkdir(parents=True)
        for f in self._state_files():
            shutil.copy2(f, dest / f.name)
        meta = self.meta
        (dest / "_snapshot.json").write_text(json.dumps(
            {"label": label, "at": now(), "version": meta.get("version"),
             "corrections": len(self.corrections()), "approved": len(self.approved())}), encoding="utf-8")
        # Keep the very first copy (the profile as created) and the most recent ones.
        snaps = self.snapshots()
        for old in snaps[1:-(MAX_SNAPSHOTS - 1)]:
            shutil.rmtree(old["path"])

    def _restore(self, snap: dict) -> None:
        for f in self._state_files():
            f.unlink()
        for f in snap["path"].iterdir():
            if f.name != "_snapshot.json":
                shutil.copy2(f, self.dir / f.name)

    def undo(self) -> dict | None:
        """Put back the files from before the last change. Returns that snapshot's info, or None."""
        snaps = self.snapshots()
        if not snaps:
            return None
        last = snaps[-1]
        self._restore(last)
        shutil.rmtree(last["path"])
        return last

    def restore_first(self) -> dict | None:
        """Go back to the profile as it was first created, and forget every snapshot."""
        snaps = self.snapshots()
        if not snaps:
            return None
        self._restore(snaps[0])
        shutil.rmtree(self.dir / SNAPSHOTS)
        return snaps[0]

    def bundle(self) -> dict:
        """Everything the web view needs, without the raw chat log."""
        return {
            "format": "textback-profile/1",
            "slug": self.slug,
            "meta": self.meta,
            "style": self.style,
            "persona": self.persona,
            "examples": self.examples(),
            "corrections": self.corrections(),
            "approved": self.approved(),
            "undo": [{"label": s.get("label"), "at": s.get("at")} for s in self.snapshots()][-1:],
            "undo_count": len(self.snapshots()),
        }


def list_profiles(base: Path | None = None) -> list[Profile]:
    root = base or PROFILES_DIR
    if not root.exists():
        return []
    return [Profile(d.name, root) for d in sorted(root.iterdir()) if (d / "meta.json").exists()]
