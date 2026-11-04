"""Create profiles, keep learning from new chats, and absorb your feedback."""
from __future__ import annotations

from pathlib import Path

from .chat_parser import Message, merge, parse_file
from .persona_builder import build_persona
from .profile_store import Profile, now
from .style_analyzer import analyze


def _rebuild(profile: Profile, messages: list[Message], meta: dict) -> dict:
    result = analyze(messages, meta["target"], meta.get("me"))
    examples = result.pop("examples")
    profile.write_jsonl("messages.jsonl", [m.to_dict() for m in messages])
    profile.write_jsonl("examples.jsonl", examples)
    profile.write_json("style.json", result)
    profile.write_json("meta.json", meta)
    persona = build_persona(meta, result, examples, meta.get("notes", ""))
    profile.path("persona.md").write_text(persona, encoding="utf-8")
    return result


def create_profile(
    chat_file: str | Path | None,
    target: str,
    name: str | None = None,
    me: str | None = None,
    relationship: str = "friend",
    notes: str = "",
    use_reference: bool = True,
    messages: list[Message] | None = None,
    source: str | None = None,
) -> Profile:
    """Learn from a chat export (`chat_file`) or from already-parsed messages (e.g. screenshots)."""
    if messages is None:
        messages = parse_file(chat_file)
        source = Path(chat_file).name
    if not any(m.sender == target for m in messages):
        raise ValueError(f"No messages from '{target}' found in {source or chat_file}")
    display = name or target
    profile = Profile(display)
    meta = {
        "name": display,
        "relationship": relationship,
        "target": target,
        "me": me,
        "notes": notes,
        "use_reference": use_reference,
        "version": 1,
        "created": now(),
        "updated": now(),
        "sources": [source or "messages"],
    }
    _rebuild(profile, messages, meta)
    return profile


def learn(profile: Profile, chat_file: str | Path | None = None,
          messages: list[Message] | None = None, source: str | None = None) -> tuple[int, int]:
    """Merge a new export (or parsed screenshots) into the profile. Returns (new_messages, version)."""
    meta = profile.meta
    old = profile.messages()
    if messages is None:
        messages, source = parse_file(chat_file), Path(chat_file).name
        merged = merge(old, messages)
    else:
        # Screenshots have no timestamps: drop only the bubbles that overlap the end of what we have.
        from .screenshot_parser import stitch
        merged = stitch(old, messages)
    added = len(merged) - len(old)
    if added:
        profile.snapshot(f"learn from {source or 'messages'}")
        meta["version"] += 1
        meta["updated"] = now()
        meta.setdefault("sources", []).append(source or "messages")
        _rebuild(profile, merged, meta)
    return added, meta["version"]


def add_note(profile: Profile, note: str) -> None:
    """Add something you know about them ("never texts after 9pm", "calls everyone 'chief'")."""
    profile.snapshot(f"note: {note.strip()[:40]}")
    meta = profile.meta
    meta["notes"] = (meta.get("notes", "") + "\n- " + note.strip()).strip()
    meta["updated"] = now()
    _rebuild(profile, profile.messages(), meta)


def correct(profile: Profile, context: str, bad: list[str] | str, good: list[str] | str) -> None:
    """Record 'they would never say <bad>, they'd say <good>'. Corrections outrank history."""
    as_list = lambda v: v if isinstance(v, list) else [s for s in v.split(" | ") if s]  # noqa: E731
    profile.snapshot(f"correction to \"{context[:40]}\"")
    profile.append_jsonl(
        "corrections.jsonl", {"context": context, "bad": as_list(bad), "good": as_list(good), "at": now()}
    )


def approve(profile: Profile, context: str, reply: list[str] | str) -> None:
    """Mark a generated reply as exactly right, so similar situations reuse it."""
    reply = reply if isinstance(reply, list) else [reply]
    profile.snapshot(f"approved reply to \"{context[:40]}\"")
    profile.append_jsonl("approved.jsonl", {"context": context, "reply": reply, "at": now()})


def reset_feedback(profile: Profile) -> dict:
    """Forget your corrections, approvals and notes; keep everything learned from the chats.

    Returns how much was cleared. Undoable with `undo`."""
    meta = profile.meta
    cleared = {"corrections": len(profile.corrections()), "approved": len(profile.approved()),
               "notes": len([n for n in meta.get("notes", "").splitlines() if n.strip()])}
    if not any(cleared.values()):
        return cleared
    profile.snapshot("reset corrections, approvals and notes")
    for name in ("corrections.jsonl", "approved.jsonl"):
        if profile.path(name).exists():
            profile.path(name).unlink()
    if cleared["notes"]:
        meta["notes"] = ""
        meta["updated"] = now()
        _rebuild(profile, profile.messages(), meta)
    return cleared


def undo(profile: Profile) -> dict | None:
    """Undo the last change (a learn, correction, approval, note or reset)."""
    snap = profile.undo()
    return snap


def reset_to_start(profile: Profile) -> dict | None:
    """Return the profile to how it was when it was first created."""
    snap = profile.restore_first()
    return snap
