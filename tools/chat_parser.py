"""Parse chat exports into a flat list of Message objects.

Supported inputs:
  * WhatsApp .txt exports (both "[date, time] Name: text" and "date, time - Name: text")
  * Plain "Name: text" transcripts (iMessage/SMS copy-paste, Discord logs, etc.)
  * CSV with sender/text/timestamp-like columns (imessage-exporter, SMS Backup, Telegram CSV)
  * JSON: a list of {sender, text, timestamp} or {"messages": [...]} (Telegram JSON export works)
"""
from __future__ import annotations

import csv
import json
import re
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path


@dataclass
class Message:
    sender: str
    text: str
    timestamp: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Message":
        return cls(d.get("sender", ""), d.get("text", ""), d.get("timestamp"))


_TIME = r"\d{1,2}:\d{2}(?::\d{2})?\s*(?:[AaPp]\.?\s?[Mm]\.?)?"
_DATE = r"\d{1,4}[./-]\d{1,2}[./-]\d{1,4}"
WHATSAPP_BRACKET = re.compile(
    rf"^\[(?P<date>{_DATE}),?\s+(?P<time>{_TIME})\]\s*(?P<sender>[^:]{{1,60}}):\s?(?P<text>.*)$"
)
WHATSAPP_DASH = re.compile(
    rf"^(?P<date>{_DATE}),?\s+(?P<time>{_TIME})\s+-\s+(?P<sender>[^:]{{1,60}}):\s?(?P<text>.*)$"
)
SIMPLE = re.compile(r"^(?P<sender>[^:\[\]\n]{1,40}):\s+(?P<text>.+)$")

SKIP_MARKERS = (
    "<media omitted>",
    "image omitted",
    "video omitted",
    "sticker omitted",
    "audio omitted",
    "gif omitted",
    "this message was deleted",
    "you deleted this message",
    "messages and calls are end-to-end encrypted",
)

_DATE_FORMATS = ["%m/%d/%y", "%m/%d/%Y", "%d/%m/%y", "%d/%m/%Y", "%Y-%m-%d", "%d.%m.%y", "%d.%m.%Y", "%Y/%m/%d"]
_TIME_FORMATS = ["%I:%M:%S %p", "%I:%M %p", "%H:%M:%S", "%H:%M"]

SENDER_KEYS = ("sender", "from", "author", "name", "sender_name", "contact", "who")
TEXT_KEYS = ("text", "message", "body", "content", "msg")
TIME_KEYS = ("timestamp", "date", "time", "datetime", "sent_at", "created_at")


def _clean(line: str) -> str:
    return line.replace(" ", " ").replace("‎", "").replace("﻿", "").rstrip("\r\n")


def parse_datetime(date: str, time: str) -> str | None:
    time = re.sub(r"\s+", " ", time.replace(".", "")).upper().strip()
    time = re.sub(r"(\d)([AP]M)$", r"\1 \2", time)
    for df in _DATE_FORMATS:
        for tf in _TIME_FORMATS:
            try:
                return datetime.strptime(f"{date} {time}", f"{df} {tf}").isoformat()
            except ValueError:
                continue
    return None


def _keep(text: str) -> bool:
    low = text.strip().lower()
    return bool(low) and not any(marker in low for marker in SKIP_MARKERS)


def parse_text(raw: str) -> list[Message]:
    lines = [_clean(line) for line in raw.splitlines()]
    sample = [line for line in lines[:200] if line.strip()]
    scores = {
        "bracket": sum(bool(WHATSAPP_BRACKET.match(line)) for line in sample),
        "dash": sum(bool(WHATSAPP_DASH.match(line)) for line in sample),
        "simple": sum(bool(SIMPLE.match(line)) for line in sample),
    }
    # WhatsApp lines also match SIMPLE, so prefer the timestamped formats when present.
    fmt = max(("bracket", "dash"), key=scores.get)
    if scores[fmt] == 0:
        fmt = "simple"
    pattern = {"bracket": WHATSAPP_BRACKET, "dash": WHATSAPP_DASH, "simple": SIMPLE}[fmt]

    messages: list[Message] = []
    for line in lines:
        match = pattern.match(line)
        if match:
            ts = parse_datetime(match["date"], match["time"]) if fmt != "simple" else None
            messages.append(Message(match["sender"].strip(), match["text"].strip(), ts))
        elif messages and line.strip():
            messages[-1].text += "\n" + line.strip()  # multi-line message continuation
    return [m for m in messages if _keep(m.text)]


def _pick(row: dict, keys: tuple[str, ...]):
    lowered = {str(k).lower().strip(): v for k, v in row.items()}
    for key in keys:
        if key in lowered and lowered[key] not in (None, ""):
            return lowered[key]
    return None


def _text_value(value) -> str:
    # Telegram JSON stores rich text as a list of strings / {"text": ...} entities.
    if isinstance(value, list):
        return "".join(part if isinstance(part, str) else part.get("text", "") for part in value)
    return "" if value is None else str(value)


def _rows_to_messages(rows) -> list[Message]:
    out = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        sender = _pick(row, SENDER_KEYS)
        text = _text_value(_pick(row, TEXT_KEYS))
        if sender and _keep(text):
            ts = _pick(row, TIME_KEYS)
            out.append(Message(str(sender).strip(), text.strip(), str(ts) if ts else None))
    return out


def parse_csv(raw: str) -> list[Message]:
    return _rows_to_messages(csv.DictReader(raw.splitlines()))


def parse_json(raw: str) -> list[Message]:
    data = json.loads(raw)
    if isinstance(data, dict):
        data = data.get("messages", [])
    return _rows_to_messages(data)


def parse_file(path: str | Path) -> list[Message]:
    path = Path(path)
    raw = path.read_text(encoding="utf-8", errors="replace")
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return parse_csv(raw)
    if suffix == ".json":
        return parse_json(raw)
    return parse_text(raw)


def participants(messages: list[Message]) -> list[tuple[str, int]]:
    return Counter(m.sender for m in messages).most_common()


def merge(existing: list[Message], new: list[Message]) -> list[Message]:
    """Append new messages, skipping exact duplicates (same sender, text and timestamp)."""
    seen = {(m.sender, m.text, m.timestamp) for m in existing}
    merged = list(existing)
    for m in new:
        key = (m.sender, m.text, m.timestamp)
        if key not in seen:
            seen.add(key)
            merged.append(m)
    return merged
