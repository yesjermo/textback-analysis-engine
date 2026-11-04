"""Generate replies in someone's voice.

Offline engine: works out what your text is asking for (permission, a "when" question, an
apology...), then either reuses their real reply to a very similar text, or composes an
answer from (a) how they usually react to that kind of text, (b) a follow-up that
mentions your topic and a time they actually use, (c) their shorthand and punctuation.
Every offline reply comes with a `why` explaining which of those happened.
"""
from __future__ import annotations

import random
import re
from collections import Counter

from .intents import (
    CONTEXTLESS, DEADLINE_HINT, DEADLINE_TIMES, DEFAULT_TIMES, FACT_INTENTS, FAMILY_NAMES, GUIDANCE, LABELS, reference_rows, TEMPLATES, Index,
    detect_intent, extract_times, extract_topic, family, last_message, personalize, tokens,
)
from .persona_builder import style_rules
from .profile_store import Profile
from .style_analyzer import EMOJI_RE

WEIGHTS = {"correction": 1.6, "approved": 1.25, "history": 1.0, "reference": 0.75}
TIME_INTENTS = {"q_when", "schedule", "q_status"}
REUSE_SCORE = 0.6      # same kind of text + clearly similar wording: send their real reply as-is
NEAR_COSINE = 0.25     # similar enough to borrow their reaction from that reply
_PREP_RE = re.compile(r"^(after|by|before|at|around|until|till)\s+", re.I)


def memory(profile: Profile, fam: str | None = None) -> list[dict]:
    """All (context -> reply) pairs, tagged with where they came from and what kind of text it was."""
    rows = [{**e, "source": "history"} for e in profile.examples()]
    rows += [{"context": c["context"], "reply": c["good"], "source": "correction"} for c in profile.corrections()]
    rows += [{"context": a["context"], "reply": a["reply"], "source": "approved"} for a in profile.approved()]
    if fam and profile.meta.get("use_reference", True):
        rows += [{**r, "source": "reference"} for r in reference_rows(fam)]
    for r in rows:
        if isinstance(r["reply"], str):
            r["reply"] = [r["reply"]]
        r["intent"] = detect_intent(last_message(r["context"]), fam)
    return rows


def rank(rows: list[dict], message: str, intent: str | None = None, fam: str | None = None) -> list[tuple[float, float, dict]]:
    """Return (score, wording_similarity, row), best first. Score mixes wording and kind of text."""
    if not rows:
        return []
    intent = intent or detect_intent(message, fam)
    index = Index([r["context"] for r in rows])
    scored = []
    for i, r in enumerate(rows):
        cos = index.cosine(message, i)
        score = (0.65 * cos + 0.35 * (r["intent"] == intent)) * WEIGHTS[r["source"]]
        scored.append((score, cos, r))
    scored.sort(key=lambda t: t[0], reverse=True)
    return scored


def retrieve(rows: list[dict], message: str, k: int = 8) -> list[tuple[float, dict]]:
    return [(score, r) for score, _, r in rank(rows, message)[:k]]


def stylize(text: str, them: dict, rng: random.Random, composed: bool = False, intent: str = "") -> str:
    t = text.strip()
    if composed:
        t = personalize(t, them)
        if them.get("capitalized_start_rate", 0) >= 0.7 and t[:1].islower():
            t = t[0].upper() + t[1:]
    if them.get("lowercase_rate", 0) >= 0.6:
        t = t.lower()
    ends = them.get("ending_punctuation", {})
    if ends.get("none", 0) >= 0.5:
        t = t.rstrip(".")
    elif composed and t and t[-1] not in ".!?" and not EMOJI_RE.search(t[-1]):
        if them.get("exclaim_rate", 0) >= 0.25 and intent in ("news", "thanks", "greeting", "done"):
            t += "!"
        elif ends.get(".", 0) >= 0.3:
            t += "."
    emojis = them.get("top_emojis") or []
    if emojis and not EMOJI_RE.search(t) and rng.random() < them.get("emoji_rate", 0) * 0.6:
        t += " " + rng.choice(emojis[:3])
    return t


def _short(text: str, intent: str) -> bool:
    return len(text.split()) <= 5 and (intent in TIME_INTENTS or not re.search(r"\d", text))


def _times(n: int) -> str:
    return "once" if n == 1 else f"{n} times"


def _reaction_bank(rows: list[dict], intent: str) -> Counter:
    """How they actually open their reply to this kind of text, e.g. permission -> 'ya np'."""
    bank: Counter = Counter()
    for r in rows:
        first = r["reply"][0] if r["reply"] else ""
        if intent in CONTEXTLESS and len(first.split()) > 2:
            continue  # "omw to facetime u" answered something else; only "ok" / "lol" travel
        if r["source"] != "reference" and r["intent"] == intent and r["reply"] and _short(first, intent):
            bank[r["reply"][0]] += 2 if r["source"] != "history" else 1
    return bank


def _pick_time(message: str, them: dict, fam: str, rng: random.Random) -> tuple[str, str]:
    mentioned = extract_times(message)
    if mentioned:
        return mentioned[0], "the time you mentioned"
    phrases = them.get("time_phrases") or []
    if DEADLINE_HINT.search(message):  # deadlines get days ("by fri"), not clock times
        phrases = [p for p in phrases if DEADLINE_TIMES.search(p)]
        if not phrases:
            return rng.choice(["by eod", "by fri", "end of the week"]), "a default deadline"
    if phrases:
        return rng.choice(phrases[:4]), "a time phrase they often use"
    return rng.choice(DEFAULT_TIMES[fam]), "a default time"


def _fill(template: str, topic: str | None, time: str, bare_time: str) -> str | None:
    if "{topic}" in template and not topic:
        return None
    # "{time} works" / "give me until {time}": drop the phrase's own "after"/"by" to avoid "until after 3".
    when = bare_time if re.search(r"(^|\b(until|till|by|at|after|before|around|do)\s+)\{time\}", template) else time
    return template.replace("{topic}", topic or "").replace("{time}", when).strip()


def _offline_reply(profile: Profile, message: str, recent: list[str], rng: random.Random) -> tuple[list[str], dict]:
    meta, them = profile.meta, profile.style.get("them", {})
    fam = family(meta.get("relationship"))
    rows = memory(profile, fam)
    intent = detect_intent(message, fam)
    topic = extract_topic(message)
    why = {"intent": intent, "read_as": LABELS.get(intent, intent), "topic": topic}

    everything = [t for t in rank(rows, message, intent, fam) if " ".join(t[2]["reply"]) not in recent]
    ranked = [t for t in everything if t[2]["source"] != "reference"]
    references = [t for t in everything if t[2]["source"] == "reference"]
    best = ranked[0] if ranked else None

    # 1. A near-identical situation already happened (or you taught one): send that reply.
    near = None
    if best:
        score, cos, row = best
        taught = row["source"] != "history"
        if (row["intent"] == intent and score >= REUSE_SCORE) or (taught and cos >= 0.5):
            source = f'{"you taught this reply" if taught else "their real reply"} to "{last_message(row["context"])}"'
            # Later bubbles can carry details from that other day ("standup moved to 9:30").
            # Drop the reply if one has numbers or times that have nothing to do with your text.
            mine = set(tokens(message))
            off_topic = [b for b in row["reply"][1:]
                         if (re.search(r"\d", b) or extract_times(b)) and not set(tokens(b)) & mine]
            extra_ok = taught or cos >= 0.8 or not off_topic
            if extra_ok:
                why.update(strategy="reused", because=f"{source} ({round(cos * 100)}% similar wording)")
                return [stylize(t, them, rng) for t in row["reply"]], why
            near = (score, cos, row)

    # 2. Compose: their reaction + a follow-up about your topic, in their style.
    tpl = TEMPLATES[fam].get(intent) or TEMPLATES[fam]["statement"]
    time, time_src = _pick_time(message, them, fam, rng)
    bare_time = _PREP_RE.sub("", time)
    near_min = 0.5 if intent in CONTEXTLESS else NEAR_COSINE
    near = near or next(((s, c, r) for s, c, r in ranked[:5] if r["intent"] == intent and c >= near_min), None)
    bank = _reaction_bank(rows, intent)
    if intent in FACT_INTENTS:
        # "why/who/what/how" answers are facts about one situation ("eng needs more time").
        # Only borrow one when the wording is close enough to be the same situation.
        bank = Counter()
        if near and near[1] < 0.45:
            near = None
    if extract_times(message):  # you named a time: don't open by proposing a different one
        bank = Counter({k: v for k, v in bank.items() if not extract_times(k)})
        if near and extract_times(near[2]["reply"][0]):
            near = None

    strong_ref = next(((s, c, r) for s, c, r in references[:5] if r["intent"] == intent and c >= 0.6), None)
    ref = strong_ref or next(((s, c, r) for s, c, r in references[:5]
                              if r["intent"] == intent and c >= (0.45 if intent in FACT_INTENTS else 0.3)), None)
    use_ref = ref and not (near and _short(near[2]["reply"][0], intent)) and (strong_ref or not bank)

    if use_ref:
        # Their own chat has nothing like this: borrow a generic reply's shape, in their style.
        why.update(strategy="reference",
                   because=f'the built-in {FAMILY_NAMES[fam]} reference reply to "{ref[2]["context"]}", '
                           f"rewritten in their style (your chat had nothing similar)")
        target = max(1, min(3, round(them.get("msgs_per_turn", 1))))
        parts = [stylize(b, them, rng, True, intent) for b in ref[2]["reply"]]
        if _one_text_writer(them):
            return [_join_long(parts)], why  # they write one fuller message
        return parts[:target], why
    if near and _short(near[2]["reply"][0], intent):
        reaction, composed = near[2]["reply"][0], False
        why["reaction_from"] = f'their reply when you said "{last_message(near[2]["context"])}"'
    elif bank:
        options = bank.most_common(4)
        reaction = rng.choices([o for o, _ in options], weights=[c for _, c in options])[0]
        composed = False
        why["reaction_from"] = f"how they usually react to {why['read_as']} ({_times(sum(bank.values()))} in your chat)"
    else:
        reacts = [f for f in (_fill(t, topic, time, bare_time) for t in tpl["react"]) if f]
        reaction, composed = rng.choice(reacts), True
        why["reaction_from"] = f"a typical {FAMILY_NAMES[fam]} reaction to {why['read_as']}, rewritten in their style"

    bubbles = [stylize(reaction, them, rng, composed, intent)]
    target = max(1, min(3, round(them.get("msgs_per_turn", 1))))
    long_writer = _one_text_writer(them)
    if long_writer:
        target = 3 if them.get("avg_words", 0) >= 10 else 2  # they write one fuller message: gather, then join
    follows = [f for f in (_fill(t, topic, time, bare_time) for t in tpl["follow"]) if f]
    # Prefer follow-ups that use your topic or a time: they make the reply about *your* text.
    rng.shuffle(follows)
    follows.sort(key=lambda f: (topic is not None and topic in f) or bare_time in f, reverse=True)
    for f in follows:
        if len(bubbles) >= target:
            break
        styled = stylize(f, them, rng, True, intent)
        if styled.lower() not in (b.lower() for b in bubbles):
            bubbles.append(styled)
    if long_writer and len(bubbles) > 1:
        bubbles = [_join_long(bubbles)]
    why["strategy"] = "composed"
    if any(bare_time in b for b in bubbles):
        why["time"] = f'"{time}" ({time_src})'
    return bubbles, why


def _one_text_writer(them: dict) -> bool:
    """Sends one fuller text per turn (about 6 words or more) instead of several short ones."""
    return them.get("avg_words", 0) >= 6 and them.get("msgs_per_turn", 1) < 1.4


def _join_long(parts: list[str]) -> str:
    """One long text from several short ones: 'Yes!' + 'where?' -> 'Yes! where?' with sentence breaks kept."""
    out = []
    trailing = re.compile(rf"\s*(?:{EMOJI_RE.pattern})+\s*$")
    # One emoji at the end, not one per piece; a piece that is only an emoji ("😂") stays.
    parts = [trailing.sub("", p) or p for p in parts[:-1]] + parts[-1:]
    for p in parts:
        p = p.strip()
        if out and out[-1][-1:] not in ".!?" and not EMOJI_RE.search(out[-1][-1:]):
            out[-1] += "."
        out.append(p[:1].upper() + p[1:] if out and out[-1][-1:] in ".!?" else p)
    return " ".join(out)


def explain(why: dict) -> str:
    """One readable line: why the offline engine said what it said."""
    if not why:
        return ""
    parts = [f"read your text as {why['read_as']}" + (f' about "{why["topic"]}"' if why.get("topic") else "")]
    if why.get("strategy") == "reused":
        parts.append(f"reused {why['because']}")
    elif why.get("strategy") == "reference":
        parts.append(f"used {why['because']}")
    else:
        parts.append(f"opened with {why['reaction_from']}")
        if why.get("time"):
            parts.append(f"used {why['time']}")
    return "; ".join(parts)


def _split(text: str) -> list[str]:
    bubbles = [line.strip().strip('"') for line in text.splitlines() if line.strip()]
    bubbles = [re.sub(r"^(THEM|[A-Z][a-z]+)\s*:\s*", "", b) for b in bubbles]
    return bubbles[:6] or ["..."]


def generate_reply(profile: Profile, history: list[dict], message: str, seed: int | None = None) -> dict:
    """history: [{"role": "me"|"them", "text": str}]. Returns {"replies": [...], "engine": str}."""
    rng = random.Random(seed)
    recent = [h["text"] for h in history[-12:] if h["role"] == "them"]
    replies, why = _offline_reply(profile, message, recent, rng)
    return {"replies": replies, "engine": "offline", "why": why, "explanation": explain(why)}


def generate_opener(profile: Profile, history: list[dict], seed: int | None = None) -> dict:
    """Let them text first, the way they usually start a conversation."""
    rng = random.Random(seed)
    starters = profile.style.get("starters") or [r["reply"] for r in profile.examples()[:20]] or [["hey"]]
    them = profile.style.get("them", {})
    return {"replies": [stylize(t, them, rng) for t in rng.choice(starters)], "engine": "offline",
            "explanation": "how they opened a conversation after a long silence in your chat"}
