"""Turn style stats into readable rules and a persona.md."""
from __future__ import annotations

RELATIONSHIPS = ("boss", "coworker", "client", "friend", "best friend", "partner", "talking stage", "ex",
                 "parent", "sibling", "other")


def relationship(value: str) -> str:
    """argparse type: accepts 'talking-stage' / 'talking_stage' / 'Talking Stage'."""
    v = value.lower().replace("-", " ").replace("_", " ").strip()
    if v not in RELATIONSHIPS:
        raise ValueError(f"relationship must be one of: {', '.join(RELATIONSHIPS)}")
    return v


def style_rules(style: dict) -> list[str]:
    """Plain-English rules derived from the numbers. Used by both engines and the web view."""
    s = style.get("them", style)
    if not s or not s.get("count"):
        return ["Not enough messages yet. Import more chat history."]
    rules = []
    avg = s.get("avg_words", 0)
    if avg <= 4:
        rules.append(f"Very short texts: about {avg} words each. One-word answers are normal.")
    elif avg <= 12:
        rules.append(f"Short, casual texts: about {avg} words each.")
    else:
        rules.append(f"Writes full, longer messages: about {avg} words each.")

    if s.get("msgs_per_turn", 1) >= 1.6:
        rules.append(f"Sends bursts: about {s['msgs_per_turn']} separate texts per turn instead of one long one.")
    else:
        rules.append("Usually sends one text per turn.")

    if s.get("lowercase_rate", 0) >= 0.6:
        rules.append("Types almost entirely in lowercase.")
    elif s.get("capitalized_start_rate", 0) >= 0.7:
        rules.append("Starts messages with a capital letter, like proper writing.")

    ends = s.get("ending_punctuation", {})
    if ends.get("none", 0) >= 0.5:
        rules.append("Usually leaves the final punctuation off.")
    if ends.get(".", 0) >= 0.3:
        rules.append("Often ends texts with a period, which reads as formal or curt.")
    if s.get("exclaim_rate", 0) >= 0.25:
        rules.append("Uses exclamation marks a lot!")
    if ends.get("ellipsis", 0) >= 0.1:
        rules.append("Trails off with '...' fairly often.")

    if s.get("emoji_rate", 0) >= 0.2 and s.get("top_emojis"):
        rules.append(f"Uses emoji in about {round(s['emoji_rate'] * 100)}% of texts, mostly {' '.join(s['top_emojis'][:4])}.")
    elif s.get("emoji_rate", 0) < 0.05:
        rules.append("Almost never uses emoji.")

    if s.get("laugh_style"):
        rules.append(f"Laughs with \"{s['laugh_style']}\".")
    if s.get("slang"):
        rules.append(f"Slang and shorthand: {', '.join(s['slang'][:8])}.")
    if s.get("top_phrases"):
        rules.append(f"Signature phrases: {', '.join(repr(p) for p in s['top_phrases'][:6])}.")
    if s.get("initiation_rate") is not None:
        if s["initiation_rate"] >= 0.6:
            rules.append(f"Usually texts first: starts {round(s['initiation_rate'] * 100)}% of your conversations.")
        elif s["initiation_rate"] <= 0.3:
            rules.append(f"Rarely texts first: starts only {round(s['initiation_rate'] * 100)}% of conversations; you usually reach out.")
    if s.get("median_reply_seconds") is not None:
        mins = s["median_reply_seconds"] / 60
        rules.append(f"Typical reply delay: {'under a minute' if mins < 1 else f'about {round(mins)} min'}.")

    you = style.get("you", {})
    if you.get("count") and s.get("avg_words"):
        ratio = s["avg_words"] / max(you.get("avg_words", 1), 0.1)
        if ratio < 0.6:
            rules.append("Replies to you much more briefly than you write to them.")
        elif ratio > 1.6:
            rules.append("Writes back at greater length than you do.")
        else:
            rules.append("Roughly matches your message length.")
    return rules


def offline_persona(meta: dict, style: dict, notes: str = "") -> str:
    rules = "\n".join(f"- {r}" for r in style_rules(style))
    them = style.get("them", {})
    words = ", ".join(them.get("top_words", [])[:15]) or "n/a"
    notes_block = f"\n## What you told me about them\n\n{notes.strip()}\n" if notes.strip() else ""
    return f"""# {meta['name']}

**Relationship to you:** {meta.get('relationship', 'other')}
**Learned from:** {style.get('message_count', 0)} messages ({them.get('count', 0)} from them)
**Version:** {meta.get('version', 1)}

## How they text

{rules}

## Words they reach for

{words}
{notes_block}
## Playing them

Reply only as {meta['name']} would, inside a text thread. Keep their length, casing,
punctuation and emoji habits. Never explain yourself or mention being an AI.
"""


def build_persona(meta: dict, style: dict, examples: list[dict], notes: str = "") -> str:
    """Write a persona from the measured style stats."""
    return offline_persona(meta, style, notes)
