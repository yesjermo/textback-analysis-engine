"""Turn chat screenshots (Instagram, TikTok, iMessage, WhatsApp, Snapchat...) into messages.

Every chat app draws your bubbles on the right and theirs on the left, so after reading the
text we only need where each bubble sits:

  1. Read text lines with their positions (OCR).
  2. Drop the header, the typing bar and app clutter (timestamps, "Seen", "Active now", ...).
  3. Group lines that belong to one bubble (stacked, left-aligned with each other).
  4. A bubble lined up with the left column is theirs; with the right column, yours.
     Centred lines (date dividers) are skipped.
  5. Stitch screenshots together, dropping bubbles repeated where you scrolled.

OCR engines, picked automatically (or with --ocr):
  vision     Apple Vision via tools/ocr_vision.swift. macOS only, nothing to install.
  tesseract  the `tesseract` command (brew install tesseract / apt install tesseract-ocr).
"""
from __future__ import annotations

from difflib import SequenceMatcher
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from .chat_parser import Message
from .intents import DATA

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".heic", ".heif", ".webp", ".gif", ".bmp", ".tif", ".tiff"}
CFG = DATA["screenshot"]
JUNK = [re.compile(rf"^(?:{p})$", re.I) for p in CFG["junk"]]
KEEP_SHORT = set(CFG["keep_short"])
STRIP_PREFIX = re.compile(CFG["strip_prefix"])  # profile-picture circles read as a stray "O"
SWIFT_SRC = Path(__file__).with_name("ocr_vision.swift")
CACHE_DIR = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "textback"


# ---- finding the images -----------------------------------------------------------

def _natural_key(path: Path):
    return [int(part) if part.isdigit() else part.lower() for part in re.split(r"(\d+)", path.name)]


def collect_images(paths: list[str | Path]) -> list[Path]:
    """Files and folders -> image files, in name order (IMG_0012 before IMG_0103)."""
    found: list[Path] = []
    for raw in paths:
        p = Path(raw).expanduser()
        if p.is_dir():
            found += sorted((f for f in p.iterdir() if f.suffix.lower() in IMAGE_EXTS), key=_natural_key)
        elif p.suffix.lower() in IMAGE_EXTS and p.exists():
            found.append(p)
        else:
            raise FileNotFoundError(f"not an image or folder: {p}")
    if not found:
        raise FileNotFoundError("no screenshots found (png, jpg, heic, webp...)")
    return found


# ---- OCR engines --------------------------------------------------------------------

def available_engines() -> list[str]:
    engines = []
    if sys.platform == "darwin" and (shutil.which("swiftc") or shutil.which("swift")):
        engines.append("vision")
    if shutil.which("tesseract"):
        engines.append("tesseract")
    return engines


def _vision_binary() -> list[str]:
    """Compile ocr_vision.swift once (a few seconds), then reuse the binary."""
    binary = CACHE_DIR / "ocr_vision"
    if shutil.which("swiftc"):
        if not binary.exists() or binary.stat().st_mtime < SWIFT_SRC.stat().st_mtime:
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            result = subprocess.run(["swiftc", "-O", str(SWIFT_SRC), "-o", str(binary)], capture_output=True, text=True)
            if result.returncode != 0:
                return ["swift", str(SWIFT_SRC)]  # fall back to interpreting the script
        return [str(binary)]
    return ["swift", str(SWIFT_SRC)]


def ocr_vision(images: list[Path]) -> list[dict]:
    result = subprocess.run(_vision_binary() + [str(i) for i in images], capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"Apple Vision OCR failed: {result.stderr.strip()}")
    return json.loads(result.stdout)


def ocr_tesseract(images: list[Path]) -> list[dict]:
    pages = []
    for image in images:
        result = subprocess.run(["tesseract", str(image), "stdout", "--psm", "11", "tsv"], capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"tesseract failed on {image}: {result.stderr.strip()}")
        rows = [r.split("\t") for r in result.stdout.splitlines()[1:] if r.count("\t") >= 11]
        page = next((r for r in rows if r[0] == "1"), None)
        width, height = (float(page[8]), float(page[9])) if page else (1.0, 1.0)
        groups: dict[tuple, dict] = {}
        for r in rows:
            if r[0] != "5" or not r[11].strip() or float(r[10]) < 0:
                continue
            key = (r[2], r[3], r[4])  # block, paragraph, line
            left, top, w, h = (float(v) for v in r[6:10])
            g = groups.setdefault(key, {"words": [], "x0": left, "x1": left + w, "y0": top, "y1": top + h})
            g["words"].append(r[11])
            g["x0"], g["x1"] = min(g["x0"], left), max(g["x1"], left + w)
            g["y0"], g["y1"] = min(g["y0"], top), max(g["y1"], top + h)
        lines = [{"text": " ".join(g["words"]), "x0": g["x0"] / width, "x1": g["x1"] / width,
                  "y0": g["y0"] / height, "y1": g["y1"] / height} for g in groups.values()]
        pages.append({"image": str(image), "width": width, "height": height, "lines": lines})
    return pages


# ---- layout -> messages ---------------------------------------------------------------

def clean_ocr(text: str) -> str:
    """Fix the usual OCR slips: '|' read for 'I', emoji read as stray symbols."""
    text = re.sub(r"(^|\s)\|(?=\s|$|')", r"\1I", text)
    text = re.sub(r"\s*[®©™¢]+\s*$", "", text)
    return text.strip()


def is_junk(text: str) -> bool:
    t = text.strip()
    if not t:
        return True
    if t.lower() in KEEP_SHORT:
        return False
    return any(rx.match(t) for rx in JUNK)


def bubbles_from_page(page: dict) -> list[dict]:
    """[{side: left|right, text}] for one screenshot, top to bottom."""
    lines = [{**ln, "text": STRIP_PREFIX.sub("", ln["text"].strip())} for ln in page["lines"]]
    lines = [ln for ln in lines if CFG["top"] <= ln["y0"] and ln["y1"] <= CFG["bottom"] and not is_junk(ln["text"])]
    if not lines:
        return []
    lines.sort(key=lambda ln: (round(ln["y0"], 3), ln["x0"]))
    heights = sorted(ln["y1"] - ln["y0"] for ln in lines)
    line_h = heights[len(heights) // 2] or 0.02

    # 3. lines stacked closely and left-aligned with each other are one bubble
    groups: list[dict] = []
    for ln in lines:
        g = groups[-1] if groups else None
        if g and ln["y0"] - g["y1"] < 0.45 * line_h and abs(ln["x0"] - g["x0"]) < 0.03:
            g["texts"].append(ln["text"].strip())
            g["x1"], g["y1"] = max(g["x1"], ln["x1"]), ln["y1"]
        else:
            groups.append({"texts": [ln["text"].strip()], "x0": ln["x0"], "x1": ln["x1"], "y0": ln["y0"], "y1": ln["y1"]})

    # 4. which column is each bubble lined up with?
    left_edge = min(g["x0"] for g in groups)
    right_edge = max(g["x1"] for g in groups)
    tol = CFG["align_tolerance"]
    out = []
    for g in groups:
        on_left = g["x0"] - left_edge < tol
        on_right = right_edge - g["x1"] < tol
        if on_left and not on_right:
            side = "left"
        elif on_right and not on_left:
            side = "right"
        elif on_left and on_right:  # a long bubble spanning the screen: whichever margin is smaller
            side = "left" if g["x0"] < 1 - g["x1"] else "right"
        else:
            continue  # centred: date dividers, "You're now connected", etc.
        text = clean_ocr(" ".join(g["texts"]))
        if text:
            out.append({"side": side, "text": text})
    return out


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", text.lower())


def same_bubble(a: Message, b: Message) -> bool:
    """Same sender and nearly the same text: OCR can read one screenshot as '7?' and the next as '77?'."""
    if a.sender != b.sender:
        return False
    x, y = _norm(a.text), _norm(b.text)
    if x == y:
        return True
    if min(len(x), len(y)) < 2:  # "7" vs "77": one stray character
        return bool(x and y) and abs(len(x) - len(y)) <= 1 and (x in y or y in x)
    return SequenceMatcher(None, x, y).ratio() >= 0.75


def stitch(existing: list[Message], new: list[Message]) -> list[Message]:
    """Append `new`, skipping bubbles it repeats from `existing` (scroll overlap, re-imported screenshots)."""
    if not new:
        return existing
    # The whole screenshot is already in there (you imported it before): nothing to add.
    for start in range(max(0, len(existing) - 400), len(existing) - len(new) + 1):
        if all(same_bubble(existing[start + i], m) for i, m in enumerate(new)):
            return existing
    for k in range(min(len(existing), len(new)), 0, -1):
        if all(same_bubble(a, b) for a, b in zip(existing[-k:], new[:k])):
            return existing + new[k:]
    return existing + new


def parse_screenshots(paths: list[str | Path], them: str = "Them", me: str = "Me",
                      engine: str = "auto") -> tuple[list[Message], str]:
    """Returns (messages, engine used). Messages have no timestamps."""
    images = collect_images(paths)
    engines = available_engines()
    if engine == "auto":
        if not engines:
            raise RuntimeError(
                "No OCR engine available. Use a Mac (Apple Vision) "
                "or install tesseract (brew install tesseract / apt install tesseract-ocr)."
            )
        engine = engines[0]
    elif engine not in engines:
        raise RuntimeError(f"OCR engine '{engine}' isn't available here. Available: {', '.join(engines) or 'none'}")

    pages = ocr_vision(images) if engine == "vision" else ocr_tesseract(images)
    messages: list[Message] = []
    for page in pages:
        new = [Message(them if b["side"] == "left" else me, b["text"]) for b in bubbles_from_page(page)]
        messages = stitch(messages, new)
    return messages, engine


def to_transcript(messages: list[Message]) -> str:
    """'Name: text' lines: easy to fix by hand, and importable with --file."""
    return "".join(f"{m.sender}: {m.text}\n" for m in messages)
