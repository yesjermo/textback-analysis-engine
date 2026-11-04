"""Measure how someone texts: length, casing, punctuation, emoji, slang, bursts, timing.

It measures both sides of the conversation: "them" (the person being modeled) and
"you" (the user). Your own style tells the reply engine how the two of you talk to
each other, for example whether they mirror your energy or answer in one word.
"""
from __future__ import annotations

import re
from collections import Counter
from datetime import datetime
from statistics import mean, median

from .chat_parser import Message

EMOJI_RE = re.compile(
    "[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F1E6-\U0001F1FF\U00002B50\U00002764]"
)
WORD_RE = re.compile(r"[A-Za-z][A-Za-z']*")

SLANG = {
    "lol", "lmao", "lmfao", "rofl", "u", "ur", "k", "kk", "tbh", "idk", "ngl", "omg", "btw",
    "pls", "plz", "thx", "ty", "np", "rn", "imo", "fr", "bruh", "haha", "hahaha", "hehe",
    "ok", "okay", "yep", "yup", "nah", "ya", "yea", "yeah", "gonna", "wanna", "gotta", "asap",
    "fyi", "eod", "eta", "wfh", "sry", "srsly", "bc", "cuz", "tho", "ikr", "smh", "wyd", "hbu",
    "omw", "w", "mtg", "cal", "def", "prob", "tmrw",
}
STOP = {
    "the", "a", "an", "and", "or", "but", "to", "of", "in", "on", "at", "for", "is", "it",
    "i", "you", "me", "my", "we", "be", "that", "this", "so", "do", "are", "was", "with",
    "have", "just", "not", "if", "can", "i'm", "it's", "your", "what", "will", "about", "up",
    "get", "as", "all", "no", "yes", "from", "there", "they", "he", "she", "them", "our",
    "were", "been", "has", "had", "did", "don't", "how", "when", "then", "too", "out", "by",
}
# Contractions typed without the apostrophe ("dont", "thats") vs. with it.
NO_APOSTROPHE = {"dont", "cant", "wont", "im", "thats", "lets", "youre", "didnt", "isnt", "ive", "whats", "doesnt", "theyre", "wasnt", "couldnt", "shouldnt"}
LAUGHS = ("haha", "hahaha", "lol", "lmao", "hehe", "😂", "🤣", "💀")


SILENCE_SECONDS = 3 * 3600  # a gap this long starts a new conversation


def _turns(messages: list[Message]) -> list[dict]:
    """Group consecutive messages from the same sender into one turn, split by long silences."""
    turns: list[dict] = []
    for m in messages:
        if turns and turns[-1]["sender"] == m.sender and not _gap_exceeds(turns[-1]["messages"][-1], m):
            turns[-1]["messages"].append(m)
        else:
            turns.append({"sender": m.sender, "messages": [m]})
    return turns


def _gap_exceeds(a: Message, b: Message) -> bool:
    ta, tb = _ts(a.timestamp), _ts(b.timestamp)
    return bool(ta and tb and (tb - ta).total_seconds() > SILENCE_SECONDS)


def _ts(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None


def text_stats(messages: list[Message]) -> dict:
    texts = [m.text.strip() for m in messages if m.text.strip()]
    if not texts:
        return {"count": 0}
    n = len(texts)
    word_lists = [WORD_RE.findall(t) for t in texts]
    lens = [len(ws) for ws in word_lists]
    lettered = [t for t in texts if re.search("[A-Za-z]", t)]

    ends: Counter = Counter()
    for t in texts:
        if t.endswith("..") or t.endswith("…"):
            ends["ellipsis"] += 1
        elif t[-1] in ".!?":
            ends[t[-1]] += 1
        elif EMOJI_RE.search(t[-1]):
            ends["emoji"] += 1
        else:
            ends["none"] += 1

    words = Counter(w.lower() for ws in word_lists for w in ws)
    content = Counter({w: c for w, c in words.items() if w not in STOP and w not in SLANG and len(w) > 2})
    bigrams: Counter = Counter()
    for ws in word_lists:
        low = [w.lower() for w in ws]
        bigrams.update(" ".join(p) for p in zip(low, low[1:]) if not all(w in STOP for w in p))
    emojis = Counter(e for t in texts for e in EMOJI_RE.findall(t))
    laughs = Counter()
    for t in texts:
        low = t.lower()
        for laugh in LAUGHS:
            if laugh in low:
                laughs[laugh] += 1
                break

    lowered = [w.lower() for ws in word_lists for w in ws]
    no_apos = sum(w in NO_APOSTROPHE for w in lowered)
    with_apos = sum(w.replace("'", "") in NO_APOSTROPHE and "'" in w for w in lowered)

    def rate(count: int, total: int = n) -> float:
        return round(count / max(total, 1), 3)

    return {
        "count": n,
        "avg_words": round(mean(lens), 2),
        "median_words": median(lens),
        "max_words": max(lens),
        "lowercase_rate": rate(sum(t == t.lower() for t in lettered), len(lettered)),
        "capitalized_start_rate": rate(sum(t[0].isupper() for t in lettered), len(lettered)),
        "all_caps_word_rate": rate(
            sum(1 for ws in word_lists for w in ws if len(w) > 2 and w.isupper()), sum(lens)
        ),
        "ending_punctuation": {k: rate(v) for k, v in ends.most_common()},
        "apostrophe_drop_rate": rate(no_apos, no_apos + with_apos) if no_apos + with_apos else 0.0,
        "question_rate": rate(sum("?" in t for t in texts)),
        "exclaim_rate": rate(sum("!" in t for t in texts)),
        "emoji_rate": rate(sum(bool(EMOJI_RE.search(t)) for t in texts)),
        "top_emojis": [e for e, _ in emojis.most_common(8)],
        "laugh_style": laughs.most_common(1)[0][0] if laughs else None,
        "slang": [w for w, _ in Counter({w: c for w, c in words.items() if w in SLANG}).most_common(10)],
        "top_words": [w for w, _ in content.most_common(25)],
        "top_phrases": [b for b, c in bigrams.most_common(40) if c > 1][:15],
    }


def analyze(messages: list[Message], target: str, me: str | None = None, max_examples: int = 400) -> dict:
    """Return style stats for `target` (them) and `me` (you), plus real reply examples."""
    them_msgs = [m for m in messages if m.sender == target]
    you_msgs = [m for m in messages if (m.sender == me if me else m.sender != target)]
    turns = _turns(messages)

    them = text_stats(them_msgs)
    you = text_stats(you_msgs)

    their_turns = [t for t in turns if t["sender"] == target]
    them["msgs_per_turn"] = round(mean(len(t["messages"]) for t in their_turns), 2) if their_turns else 1.0
    openers = Counter()
    for t in their_turns:
        first = WORD_RE.findall(t["messages"][0].text)
        if first:
            openers[first[0].lower()] += 1
    them["turn_openers"] = [w for w, _ in openers.most_common(8)]
    from .intents import extract_times  # local import: intents depends on this module

    times = Counter(t.lower() for m in them_msgs for t in extract_times(m.text))
    # Phrases like "after 3" / "by fri" first: they work as answers, a bare "9:30" usually doesn't.
    ranked = sorted(times.items(), key=lambda kv: (not re.match(r"(after|by|before|at|around|until|till) ", kv[0]), -kv[1]))
    them["time_phrases"] = [t for t, _ in ranked[:8]]

    latencies, hours, examples, conversation_starters = [], Counter(), [], []
    for i, turn in enumerate(turns):
        if turn["sender"] != target:
            continue
        start = _ts(turn["messages"][0].timestamp)
        if start:
            hours[start.hour] += len(turn["messages"])
        reply = [m.text for m in turn["messages"]]
        prev = turns[i - 1] if i else None
        if prev is None or prev["sender"] == target:
            conversation_starters.append(reply)  # they opened the chat after a silence
            continue
        prev_end = _ts(prev["messages"][-1].timestamp)
        if start and prev_end:
            gap = (start - prev_end).total_seconds()
            if 0 <= gap < SILENCE_SECONDS:
                latencies.append(gap)
            elif gap >= SILENCE_SECONDS:
                conversation_starters.append(reply)  # they picked the chat back up after a long silence
        examples.append({"context": " / ".join(m.text for m in prev["messages"][-3:]), "reply": reply})

    them["median_reply_seconds"] = round(median(latencies)) if latencies else None
    # Who starts conversations: the first turn after a long silence (or the very first turn).
    starts = [t["sender"] for i, t in enumerate(turns)
              if i == 0 or _gap_exceeds(turns[i - 1]["messages"][-1], t["messages"][0])]
    them["initiation_rate"] = round(starts.count(target) / len(starts), 2) if len(starts) >= 3 else None
    them["active_hours"] = [h for h, _ in hours.most_common(5)]

    return {
        "target": target,
        "me": me,
        "message_count": len(messages),
        "them": them,
        "you": you,
        "examples": examples[-max_examples:],
        "starters": conversation_starters[-30:],
    }
