"""Measure the texting features of both sides of a chat.

    compute_features(messages, target, me, relationship) -> dict

Everything here is counted from the messages, nothing is guessed. The same keys are computed in
the browser by web/app.js (computeFeatures), so the CLI, the server and the web view agree.

Per side ("them" and "you"):
  volume      messages, words, chars
  length      avg / median / p90 words per text, avg chars, a length histogram
  rhythm      texts per turn, longest burst, share of turns with 2+ texts, active hours and weekdays
  style       lowercase, capitalised starts, ALL-CAPS words, how texts end, ? and ! rates, a formality score
  emoji       share of texts with emoji, emoji per 100 words, distinct emoji, the favourites
  words       vocabulary size, MATTR (vocabulary richness, 0-1), average word length, slang rate,
              top words and phrases, laugh style and rate
  tone        share of texts with a positive or a negative word (a rough word-list reading)
  kinds       what kinds of text they send, by the same reading the reply engine uses

Shared: the date span, active days, who sends more, who texts first, reply delays on both sides.
"""
from __future__ import annotations

import re
from collections import Counter
from statistics import mean, median

from .chat_parser import Message
from .intents import DATA, detect_intent, family
from .style_analyzer import EMOJI_RE, LAUGHS, SLANG, STOP, WORD_RE, _gap_exceeds, _ts, _turns

LENGTH_BINS = [("0", 0, 0), ("1", 1, 1), ("2-3", 2, 3), ("4-6", 4, 6), ("7-12", 7, 12), ("13-25", 13, 25), ("26+", 26, 10**9)]
POSITIVE = set(DATA["sentiment"]["positive"])
NEGATIVE = set(DATA["sentiment"]["negative"])
WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
MATTR_WINDOW = 50


def _pct(part: float, whole: float) -> float:
    return round(100 * part / whole, 1) if whole else 0.0


def _quantile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    s = sorted(values)
    return s[min(len(s) - 1, int(q * (len(s) - 1) + 0.5))]


def mattr(words: list[str], window: int = MATTR_WINDOW) -> float | None:
    """Moving-average type-token ratio: vocabulary richness that doesn't fall just because a chat is long."""
    if len(words) < window:
        return round(len(set(words)) / len(words), 3) if words else None
    ratios = [len(set(words[i:i + window])) / window for i in range(len(words) - window + 1)]
    return round(mean(ratios), 3)


def side_features(msgs: list[Message], turns: list[dict], sender: str, fam: str) -> dict:
    texts = [m.text.strip() for m in msgs if m.text.strip()]
    n = len(texts)
    if not n:
        return {"messages": 0}
    word_lists = [WORD_RE.findall(t) for t in texts]
    words = [w.lower() for ws in word_lists for w in ws]
    lens = [len(ws) for ws in word_lists]
    lettered = [t for t in texts if re.search("[A-Za-z]", t)]

    ends: Counter = Counter()
    for t in texts:
        if t.endswith("..") or t.endswith("…"):
            ends["..."] += 1
        elif t[-1] in ".!?":
            ends[t[-1]] += 1
        elif EMOJI_RE.search(t[-1]):
            ends["emoji"] += 1
        else:
            ends["none"] += 1

    emojis = [e for t in texts for e in EMOJI_RE.findall(t)]
    emoji_counts = Counter(emojis)
    content = Counter(w for w in words if w not in STOP and w not in SLANG and len(w) > 2)
    bigrams: Counter = Counter()
    for ws in word_lists:
        low = [w.lower() for w in ws]
        bigrams.update(" ".join(p) for p in zip(low, low[1:]) if not all(w in STOP for w in p))
    laughs = Counter()
    for t in texts:
        low = t.lower()
        hit = next((laugh for laugh in LAUGHS if laugh in low), None)
        if hit:
            laughs[hit] += 1

    my_turns = [t for t in turns if t["sender"] == sender]
    sizes = [len(t["messages"]) for t in my_turns]

    hours = [0] * 24
    weekdays = [0] * 7
    for m in msgs:
        ts = _ts(m.timestamp)
        if ts:
            hours[ts.hour] += 1
            weekdays[ts.weekday()] += 1

    lowercase = _pct(sum(t == t.lower() for t in lettered), len(lettered))
    capital = _pct(sum(t[0].isupper() for t in lettered), len(lettered))
    slang = _pct(sum(w in SLANG for w in words), len(words))
    punct_end = 100 - _pct(ends["none"] + ends["emoji"], n)
    avg_word_len = round(mean(len(w) for w in words), 2) if words else 0.0
    # 0-100: capitalised starts, ending punctuation, few lowercase-only texts, little slang, longer words.
    formality = round(mean([
        capital, punct_end, 100 - lowercase, max(0.0, 100 - slang * 5), min(100.0, max(0.0, (avg_word_len - 3) * 50)),
    ]))

    kinds = Counter(detect_intent(t, fam) for t in texts)

    return {
        "messages": n,
        "words": len(words),
        "chars": sum(len(t) for t in texts),
        "avg_words": round(mean(lens), 2),
        "median_words": median(lens),
        "p90_words": _quantile(lens, 0.9),
        "avg_chars": round(mean(len(t) for t in texts), 1),
        "length_bins": {label: _pct(sum(lo <= x <= hi for x in lens), n) for label, lo, hi in LENGTH_BINS},
        "texts_per_turn": round(mean(sizes), 2) if sizes else 1.0,
        "max_burst": max(sizes) if sizes else 1,
        "burst_share": _pct(sum(s >= 2 for s in sizes), len(sizes)),
        "lowercase_pct": lowercase,
        "capital_start_pct": capital,
        "caps_word_pct": _pct(sum(1 for ws in word_lists for w in ws if len(w) > 2 and w.isupper()), len(words)),
        "endings_pct": {k: _pct(ends[k], n) for k in (".", "!", "?", "...", "emoji", "none")},
        "question_pct": _pct(sum("?" in t for t in texts), n),
        "exclaim_pct": _pct(sum("!" in t for t in texts), n),
        "multi_exclaim_pct": _pct(sum("!!" in t for t in texts), n),
        "formality": formality,
        "emoji_pct": _pct(sum(bool(EMOJI_RE.search(t)) for t in texts), n),
        "emoji_per_100_words": round(100 * len(emojis) / len(words), 1) if words else 0.0,
        "distinct_emojis": len(emoji_counts),
        "top_emojis": [e for e, _ in emoji_counts.most_common(6)],
        "vocab_size": len(set(words)),
        "mattr": mattr(words),
        "avg_word_len": avg_word_len,
        "slang_pct": slang,
        "top_words": [w for w, _ in content.most_common(12)],
        "top_phrases": [b for b, c in bigrams.most_common(30) if c > 1][:8],
        "laugh_style": laughs.most_common(1)[0][0] if laughs else None,
        "laugh_pct": _pct(sum(laughs.values()), n),
        "positive_pct": _pct(sum(any(w in POSITIVE for w in ws) for ws in ([x.lower() for x in y] for y in word_lists)), n),
        "negative_pct": _pct(sum(any(w in NEGATIVE for w in ws) for ws in ([x.lower() for x in y] for y in word_lists)), n),
        "hours": hours,
        "weekdays": weekdays,
        "kinds": dict(kinds.most_common(10)),
    }


def _reply_delays(turns: list[dict], responder: str) -> list[float]:
    """Seconds from the end of the other side's turn to the start of `responder`'s reply, same conversation only."""
    out = []
    for prev, cur in zip(turns, turns[1:]):
        if cur["sender"] != responder or prev["sender"] == responder:
            continue
        a, b = _ts(prev["messages"][-1].timestamp), _ts(cur["messages"][0].timestamp)
        if a and b and not _gap_exceeds(prev["messages"][-1], cur["messages"][0]) and b >= a:
            out.append((b - a).total_seconds())
    return out


def compute_features(messages: list[Message], target: str, me: str | None, relationship: str | None = None) -> dict:
    fam = family(relationship)
    them_msgs = [m for m in messages if m.sender == target]
    you_msgs = [m for m in messages if (m.sender == me if me else m.sender != target)]
    you_name = me or "You"
    turns = _turns(messages)
    starts = [t["sender"] for i, t in enumerate(turns) if i == 0 or _gap_exceeds(turns[i - 1]["messages"][-1], t["messages"][0])]
    stamps = [_ts(m.timestamp) for m in messages]
    stamps = [s for s in stamps if s]
    them_delay, you_delay = _reply_delays(turns, target), _reply_delays(turns, you_name if me else None)
    if not me:  # without a name for you, everyone who isn't them counts as you
        you_delay = [d for s in {m.sender for m in you_msgs} for d in _reply_delays(turns, s)]

    def secs(values, q):
        v = _quantile(values, q)
        return round(v) if v is not None else None

    return {
        "format": "textback-features/1",
        "target": target,
        "me": me,
        "relationship": relationship,
        "shared": {
            "messages": len(messages),
            "first": min(stamps).date().isoformat() if stamps else None,
            "last": max(stamps).date().isoformat() if stamps else None,
            "days_span": (max(stamps).date() - min(stamps).date()).days + 1 if stamps else None,  # calendar days
            "active_days": len({s.date() for s in stamps}) if stamps else None,
            "conversations": len(starts),
            "them_share_pct": _pct(len(them_msgs), len(them_msgs) + len(you_msgs)),
            "they_start_pct": _pct(starts.count(target), len(starts)) if len(starts) >= 3 else None,
            "them_reply_median_s": secs(them_delay, 0.5),
            "them_reply_p90_s": secs(them_delay, 0.9),
            "you_reply_median_s": secs(you_delay, 0.5),
            "you_reply_p90_s": secs(you_delay, 0.9),
            "has_timestamps": bool(stamps),
        },
        "them": side_features(them_msgs, turns, target, fam),
        "you": side_features(you_msgs, turns, me, fam) if me else side_features(you_msgs, turns, you_msgs[0].sender if you_msgs else "", fam),
    }


# ---- flat rows for CSV --------------------------------------------------------------

def flat_row(name: str, feats: dict) -> dict:
    """One CSV row per person: shared columns, then them_* and you_* columns."""
    row = {"name": name, "relationship": feats.get("relationship")}
    for k, v in feats["shared"].items():
        row[k] = v
    for side in ("them", "you"):
        for k, v in feats[side].items():
            if isinstance(v, dict):
                for kk, vv in v.items():
                    row[f"{side}_{k}_{kk}"] = vv
            elif isinstance(v, list):
                row[f"{side}_{k}"] = " ".join(str(x) for x in v) if k not in ("hours", "weekdays") else ";".join(map(str, v))
            else:
                row[f"{side}_{k}"] = v
    return row


# ---- the terminal report ------------------------------------------------------------

SPARK = " ▁▂▃▄▅▆▇█"
KIND_NAMES = {"statement": "other"}


def _spark(values: list[int]) -> str:
    top = max(values) if values else 0
    return "".join(SPARK[0 if not v else max(1, round(8 * v / top))] for v in values) if top else ""


def _dur(seconds: float | None) -> str:
    if seconds is None:
        return "-"
    if seconds < 60:
        return f"{round(seconds)}s"
    if seconds < 3600:
        return f"{round(seconds / 60)} min"
    return f"{seconds / 3600:.1f} h"


def _v(x, unit: str = "") -> str:
    if x is None:
        return "-"
    return f"{x}{unit}"


def format_report(name: str, f: dict) -> str:
    t, y, s = f["them"], f["you"], f["shared"]
    you = f.get("me") or "You"
    out = []
    w = out.append

    def row(label: str, a, b, unit: str = ""):
        w(f"  {label:26s} {_v(a, unit):>12s}   {_v(b, unit):>12s}")

    w(f"{name} ({f.get('relationship') or 'contact'}) and {you}")
    if s["has_timestamps"]:
        w(f"{s['messages']} messages, {s['first']} to {s['last']} ({s['days_span']} days, {s['active_days']} with texts), "
          f"{s['conversations']} conversations")
    else:
        w(f"{s['messages']} messages. This export has no timestamps, so timing features are left out.")
    w("")
    w(f"  {'':26s} {name[:12]:>12s}   {you[:12]:>12s}")
    w("Volume")
    row("messages", t["messages"], y.get("messages"))
    row("share of the chat", s["them_share_pct"], round(100 - s["them_share_pct"], 1), "%")
    w("Length")
    row("words per text (avg)", t["avg_words"], y.get("avg_words"))
    row("words per text (median)", t["median_words"], y.get("median_words"))
    row("words per text (90th pct)", t["p90_words"], y.get("p90_words"))
    row("characters per text", t["avg_chars"], y.get("avg_chars"))
    w("Rhythm")
    row("texts per turn", t["texts_per_turn"], y.get("texts_per_turn"))
    row("longest burst", t["max_burst"], y.get("max_burst"))
    row("turns with 2+ texts", t["burst_share"], y.get("burst_share"), "%")
    if s["has_timestamps"]:
        row("texts first", s["they_start_pct"], None if s["they_start_pct"] is None else round(100 - s["they_start_pct"], 1), "%")
        w(f"  {'reply delay (median)':26s} {_dur(s['them_reply_median_s']):>12s}   {_dur(s['you_reply_median_s']):>12s}")
        w(f"  {'reply delay (90th pct)':26s} {_dur(s['them_reply_p90_s']):>12s}   {_dur(s['you_reply_p90_s']):>12s}")
    w("Style")
    row("all-lowercase texts", t["lowercase_pct"], y.get("lowercase_pct"), "%")
    row("capitalised starts", t["capital_start_pct"], y.get("capital_start_pct"), "%")
    row("ALL-CAPS words", t["caps_word_pct"], y.get("caps_word_pct"), "%")
    for k, label in ((".", "end with a period"), ("!", "end with !"), ("?", "end with ?"), ("none", "no ending punctuation")):
        row(label, t["endings_pct"][k], y.get("endings_pct", {}).get(k), "%")
    row("multiple !! ", t["multi_exclaim_pct"], y.get("multi_exclaim_pct"), "%")
    row("formality (0-100)", t["formality"], y.get("formality"))
    w("Emoji and words")
    row("texts with emoji", t["emoji_pct"], y.get("emoji_pct"), "%")
    row("emoji per 100 words", t["emoji_per_100_words"], y.get("emoji_per_100_words"))
    row("distinct emoji", t["distinct_emojis"], y.get("distinct_emojis"))
    row("vocabulary (unique words)", t["vocab_size"], y.get("vocab_size"))
    row("richness (MATTR, 0-1)", t["mattr"], y.get("mattr"))
    row("average word length", t["avg_word_len"], y.get("avg_word_len"))
    row("slang (% of words)", t["slang_pct"], y.get("slang_pct"), "%")
    row("texts with a laugh", t["laugh_pct"], y.get("laugh_pct"), "%")
    w("Tone (word list, rough)")
    row("texts with a positive word", t["positive_pct"], y.get("positive_pct"), "%")
    row("texts with a negative word", t["negative_pct"], y.get("negative_pct"), "%")
    w("")
    w(f"{name}'s favourites")
    w(f"  emoji    {' '.join(t['top_emojis']) or '-'}")
    w(f"  laugh    {t['laugh_style'] or '-'}")
    w(f"  words    {', '.join(t['top_words']) or '-'}")
    w(f"  phrases  {', '.join(t['top_phrases']) or '-'}")
    w("  lengths  " + "  ".join(f"{k} word{'' if k == '1' else 's'} {v}%" for k, v in t["length_bins"].items()))
    kinds = ", ".join(f"{KIND_NAMES.get(k, k.replace('_', ' '))} {v}" for k, v in t["kinds"].items())
    w(f"  kinds    {kinds}")
    if s["has_timestamps"]:
        w("")
        w(f"When {name} texts (hour of day, 0-23)")
        w(f"  {_spark(t['hours'])}")
        w(f"  0     6     12    18   23")
        days = "  ".join(f"{d} {n}" for d, n in zip(WEEKDAYS, t["weekdays"]))
        w(f"  {days}")
    return "\n".join(out)


COMPARE_ROWS = [
    ("messages", lambda f: f["them"]["messages"]),
    ("words per text", lambda f: f["them"]["avg_words"]),
    ("texts per turn", lambda f: f["them"]["texts_per_turn"]),
    ("texts first %", lambda f: f["shared"]["they_start_pct"]),
    ("reply delay", lambda f: _dur(f["shared"]["them_reply_median_s"])),
    ("lowercase %", lambda f: f["them"]["lowercase_pct"]),
    ("formality", lambda f: f["them"]["formality"]),
    ("emoji %", lambda f: f["them"]["emoji_pct"]),
    ("richness", lambda f: f["them"]["mattr"]),
    ("slang %", lambda f: f["them"]["slang_pct"]),
    ("positive %", lambda f: f["them"]["positive_pct"]),
    ("laugh", lambda f: f["them"]["laugh_style"]),
    ("top emoji", lambda f: " ".join(f["them"]["top_emojis"][:3])),
]


def format_comparison(named: list[tuple[str, dict]]) -> str:
    width = max(10, *(len(n) for n, _ in named)) + 2
    lines = [f"{'':16s}" + "".join(f"{n[:width - 2]:>{width}s}" for n, _ in named)]
    for label, get in COMPARE_ROWS:
        lines.append(f"{label:16s}" + "".join(f"{_v(get(f)):>{width}s}" for _, f in named))
    return "\n".join(lines)
