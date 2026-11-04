"""Understand what a text is asking for, so the offline engine can answer it.

  detect_intent("when is the deadline?")        -> "q_when"
  extract_topic("can you review the budget sheet") -> "budget sheet"
  extract_times("let's do after 3 tomorrow")       -> ["after 3", "tomorrow"]

The patterns, synonyms and templates live in reply_data.json, which web/app.js shares.
"""
from __future__ import annotations

import json
import math
import re
from collections import Counter
from pathlib import Path

from .style_analyzer import STOP

DATA = json.loads(Path(__file__).with_name("reply_data.json").read_text(encoding="utf-8"))
INTENTS = [(name, re.compile(pattern, re.I)) for name, pattern in DATA["intents"]]
LABELS: dict[str, str] = DATA["intent_labels"]
SYNONYMS: dict[str, str] = DATA["synonyms"]
NOUN_HEADS = set(DATA["noun_heads"])
GENERIC = set(DATA["generic_nouns"])
ADJECTIVES = set(DATA["adjectives"])
FACT_INTENTS = set(DATA["fact_intents"])
CONTEXTLESS = set(DATA["contextless_intents"])  # "ok", "lol": a real reply to these depends on the moment
LAUGH_WORD = re.compile(r"\b(lol|lmao+|lmfao|haha(ha)*)\b", re.I)
FAMILIES: dict[str, list[str]] = DATA["families"]
FAMILY_ONLY: dict[str, list[str]] = DATA["family_only"]
GUIDANCE: dict[str, str] = DATA["guidance"]
TEMPLATES = DATA["templates"]
DEFAULT_TIMES = DATA["default_times"]
WH_START = re.compile(DATA["wh_start"], re.I)
_BY_NAME = dict(INTENTS)
WH_FIRST = [(n, _BY_NAME[n]) for n in DATA["wh_first"]]
DEADLINE_HINT = re.compile(DATA["deadline_hint"], re.I)
DEADLINE_TIMES = re.compile(DATA["deadline_times"], re.I)
SLANG_SWAPS = [(re.compile(p, re.I), repl, needs) for p, repl, needs in DATA["slang_swaps"]]

_DAYS = r"(?:mon|tues?|wed|thu(?:rs?)?|fri|sat|sun)(?:day)?"
_WORD_TIME = rf"(?:noon|lunch|eod|tomorrow|tmrw|tonight|next week|this week|later today|end of (?:the )?day|{_DAYS})"
_CLOCK = r"\d{1,2}(?::\d{2})?\s?(?:am|pm)|\d{1,2}:\d{2}"
_PREP = rf"(?:after|by|before|at|around|until|till)\s+(?:{_CLOCK}|\d{{1,2}}\b|{_WORD_TIME})"
TIME_RE = re.compile(rf"\b(?:{_PREP}|{_CLOCK}|{_WORD_TIME})\b", re.I)
TOPIC_RE = re.compile(r"\b(?:the|my|our|this|that|your|ur)\s+([a-z][a-z0-9'-]*(?:\s+[a-z][a-z0-9'-]*){0,2})")
TOKEN_RE = re.compile(r"[a-z0-9']+")
REFERENCE_DIR = Path(__file__).resolve().parent.parent / "reference"
FAMILY_NAMES = {"work": "work", "personal": "friends & family", "ex": "ex", "talking_stage": "talking-stage"}
_REFERENCE_CACHE: dict[str, list[dict]] = {}


def reference_rows(fam: str) -> list[dict]:
    """Generic example exchanges for this kind of relationship (reference/<family>.jsonl)."""
    if fam not in _REFERENCE_CACHE:
        path = REFERENCE_DIR / f"{fam}.jsonl"
        rows = []
        if path.exists():
            rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        _REFERENCE_CACHE[fam] = rows
    return [dict(r) for r in _REFERENCE_CACHE[fam]]


def family(relationship: str | None) -> str:
    """Which reply style a relationship uses: work, ex, talking_stage, or personal."""
    rel = (relationship or "").lower().replace("-", " ").replace("_", " ")
    for fam, members in FAMILIES.items():
        if rel in members:
            return fam
    return "personal"


def detect_intent(text: str, fam: str | None = None) -> str:
    t = text.lower().strip()
    # "where can I find..." is a where-question, not a permission request.
    order = WH_FIRST + INTENTS if WH_START.search(t) else INTENTS
    for name, rx in order:
        if fam and name in FAMILY_ONLY and fam not in FAMILY_ONLY[name]:
            continue  # a boss asking "why did you leave early" isn't a relationship talk
        if rx.search(t):
            # "did you send it?" is a question about something being done, not you reporting it.
            if name == "done" and t.endswith("?"):
                return "yesno"
            # "did you send it?" asks whether something happened; it isn't asking you to do it.
            if name == "request" and re.match(r"(did|have|has|do|does) (you|u|they|we|he|she)\b", t):
                return "yesno"
            return name
    return "statement"


def last_message(context: str) -> str:
    """Stored contexts join up to 3 texts with ' / '; the last one is what they replied to."""
    return context.split(" / ")[-1]


def extract_times(text: str) -> list[str]:
    return [m.group(0).strip() for m in TIME_RE.finditer(text)]


def extract_topic(text: str) -> str | None:
    for m in TOPIC_RE.finditer(text.lower()):
        words = m.group(1).split()
        if words[0] in ADJECTIVES and len(words) > 1:  # "the new logo" -> "logo"
            words = words[1:]
        first = words[0]
        if first in STOP or first in GENERIC or TIME_RE.fullmatch(first):
            continue
        topic = [first]
        for w in words[1:]:  # "budget sheet", "q2 budget sheet"
            if w not in NOUN_HEADS:
                break
            topic.append(w)
        return " ".join(topic)
    return None


# ---- similarity ----------------------------------------------------------------

def tokens(text: str, keep_stop: bool = False) -> list[str]:
    out = []
    for w in TOKEN_RE.findall(text.lower()):
        w = SYNONYMS.get(w, w)
        if w in STOP and not keep_stop:
            continue
        if len(w) > 4:
            for suffix in ("ing", "ed", "es", "s"):
                if w.endswith(suffix):
                    w = w[: -len(suffix)]
                    break
        out.append(SYNONYMS.get(w, w))
    return out


class Index:
    """TF-IDF over stored contexts. Rare shared words ('budget', 'dentist') count more than common ones."""

    def __init__(self, contexts: list[str]):
        msgs = [last_message(c) for c in contexts]
        self.n = len(msgs)
        # Two views: content words only, and every word (for texts like "what are we?").
        self.views = {}
        for keep in (False, True):
            docs = [Counter(tokens(m, keep)) for m in msgs]
            df: Counter = Counter()
            for d in docs:
                df.update(d.keys())
            idf = {w: math.log((self.n + 1) / (c + 1)) + 1 for w, c in df.items()}
            self.views[keep] = (idf, [self._vec(d, idf) for d in docs])

    def _vec(self, counts: Counter, idf: dict[str, float]) -> dict[str, float]:
        default = math.log(self.n + 1) + 1
        return {w: c * idf.get(w, default) for w, c in counts.items()}

    def cosine(self, query: str, i: int) -> float:
        content = tokens(query)
        keep = not content  # nothing but common words: compare every word instead
        idf, vecs = self.views[keep]
        q = self._vec(Counter(tokens(query, keep)), idf)
        d = vecs[i]
        dot = sum(v * d.get(w, 0.0) for w, v in q.items())
        if not dot:
            return 0.0
        norm = math.sqrt(sum(v * v for v in q.values())) * math.sqrt(sum(v * v for v in d.values()))
        return dot / norm


# ---- style transfer for composed text --------------------------------------------

def personalize(text: str, them: dict) -> str:
    """Rewrite neutral template text with their shorthand ('you' -> 'u' if they use 'u')."""
    used = set(them.get("slang", [])) | set(them.get("top_words", []))
    for rx, repl, needs in SLANG_SWAPS:
        if needs in used:
            text = rx.sub(repl, text)
    if them.get("apostrophe_drop_rate", 0) >= 0.5:
        text = text.replace("'", "")
    if them.get("laugh_style"):  # laugh the way they do: "lol" becomes "😂" for someone who laughs in emoji
        text = LAUGH_WORD.sub(them["laugh_style"], text)
    return text
