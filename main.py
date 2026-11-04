#!/usr/bin/env python3
"""TextBack Analysis Engine CLI: learn how your boss or friends text, analyse it, then text with them.

  python3 main.py participants chat.txt
  python3 main.py create --file chat.txt --target "Dana" --me "Alex" --relationship boss
  python3 main.py chat dana
  python3 main.py learn dana --file newer_chat.txt
  python3 main.py serve
"""
from __future__ import annotations

import argparse
import json
import random
import shutil
import sys
import tempfile
import time
from pathlib import Path

from tools import learner
from tools.chat_parser import parse_file, participants
from tools.persona_builder import RELATIONSHIPS, relationship, style_rules
from tools.profile_store import Profile, list_profiles
from tools.reply_engine import generate_opener, generate_reply
from tools.screenshot_parser import parse_screenshots, to_transcript

CHAT_HELP = """commands:
  /fix <text>   that's not what they'd say; save what they WOULD say (use ' | ' between bubbles)
  /good         that reply was spot-on; remember it
  /note <fact>  teach a fact or habit ("never texts on weekends")
  /nudge        let them text you first
  /why          explain how the last reply was chosen
  /undo         undo your last correction, approval or note
  /reset        clear this conversation
  /forget       forget your corrections, approvals and notes for this person
  /style        show their style rules
  /quit         leave
"""


def _load(slug: str) -> Profile:
    profile = Profile(slug)
    if not profile.exists():
        names = ", ".join(p.slug for p in list_profiles()) or "none yet"
        sys.exit(f"No profile '{slug}'. Profiles: {names}")
    return profile


def _pick_sender(options: list[tuple[str, int]], prompt: str, exclude: str | None = None) -> str:
    choices = [o for o in options if o[0] != exclude]
    for i, (name, count) in enumerate(choices, 1):
        print(f"  {i}. {name} ({count} messages)")
    while True:
        raw = input(prompt).strip()
        if raw.isdigit() and 1 <= int(raw) <= len(choices):
            return choices[int(raw) - 1][0]
        print("  pick a number from the list")


def _print_rules(profile: Profile) -> None:
    meta = profile.meta
    print(f"\n{meta['name']} ({meta['relationship']}), v{meta['version']}")
    for rule in style_rules(profile.style):
        print(f"  • {rule}")


def cmd_participants(args):
    for name, count in participants(parse_file(args.file)):
        print(f"{count:6d}  {name}")


def _read_screenshots(args, them: str, me: str):
    messages, engine = parse_screenshots(args.screenshots, them=them, me=me, engine=args.ocr)
    if not messages:
        sys.exit("Couldn't find any chat bubbles in those screenshots. Try a different --ocr engine, or crop to the conversation.")
    ours = sum(m.sender == them for m in messages)
    print(f"Read {len(messages)} bubbles from {len(args.screenshots)} path(s) with {engine} OCR "
          f"({ours} from {them}, {len(messages) - ours} from {me}).")
    return messages, f"screenshots ({engine})"


SAMPLES = Path(__file__).resolve().parent / "examples" / "samples" / "samples.json"


def _samples() -> list[dict]:
    return json.loads(SAMPLES.read_text(encoding="utf-8"))


def cmd_samples(_args):
    print("Sample people (all fictional). Try one with: python3 main.py create --sample <id>\n")
    for s in _samples():
        print(f"  {s['id']:8s} {s['relationship']:14s} {s['messages']:4d} msgs  {s['format']:20s} {s['about']}")


def cmd_create(args):
    if args.sample:
        found = {s["id"]: s for s in _samples()}
        if args.sample not in found:
            sys.exit(f"No sample '{args.sample}'. Samples: {', '.join(found)}")
        s = found[args.sample]
        args.file = str(Path(__file__).resolve().parent / s["file"])
        args.target, args.me = s["target"], s["me"]
        args.name = args.name or s["name"]
        if args.relationship == "friend":  # the default: use the sample's own
            args.relationship = s["relationship"]
    if bool(args.file) == bool(args.screenshots):
        sys.exit("Give either --file <chat export> or --screenshots <images or folder>.")
    if args.screenshots:
        them = args.name or args.target or "Them"
        me = args.me or "Me"
        messages, source = _read_screenshots(args, them, me)
        profile = learner.create_profile(None, them, args.name or them, me, args.relationship, args.notes or "",
                                         use_reference=not args.no_reference, messages=messages, source=source)
        print(f"Created profile '{profile.slug}'.")
        _print_rules(profile)
        print(f"\nCheck what was read: profiles/{profile.slug}/messages.jsonl  ·  Next: python3 main.py chat {profile.slug}")
        return
    target, me = args.target, args.me
    if not target or not me:
        people = participants(parse_file(args.file))
        if not people:
            sys.exit("Couldn't find any messages in that file. See INSTALL.md#exporting-chats.")
        if not target:
            print("Who should TextBack learn to be?")
            target = _pick_sender(people, "them > ")
        if not me and len(people) > 1:
            print("Which one is you?")
            me = _pick_sender(people, "you > ", exclude=target)
    profile = learner.create_profile(args.file, target, args.name, me, args.relationship, args.notes or "",
                                     use_reference=not args.no_reference)
    print(f"Created profile '{profile.slug}'.")
    _print_rules(profile)
    print(f"\nNext: python3 main.py chat {profile.slug}")


def cmd_learn(args):
    profile = _load(args.slug)
    before = style_rules(profile.style)
    if bool(args.file) == bool(args.screenshots):
        sys.exit("Give either --file <chat export> or --screenshots <images or folder>.")
    if args.screenshots:
        meta = profile.meta
        messages, source = _read_screenshots(args, meta["target"], meta.get("me") or "Me")
        added, version = learner.learn(profile, messages=messages, source=source)
    else:
        added, version = learner.learn(profile, args.file)
    if not added:
        print("Nothing new in that file; profile unchanged.")
        return
    print(f"Learned {added} new messages. {profile.meta['name']} is now v{version}.")
    after = style_rules(profile.style)
    for rule in after:
        print(f"  {'+' if rule not in before else ' '} {rule}")


def cmd_note(args):
    profile = _load(args.slug)
    learner.add_note(profile, args.fact)
    print("Noted. Persona rebuilt.")


def cmd_reference(args):
    profile = _load(args.slug)
    meta = profile.meta
    meta["use_reference"] = args.state == "on"
    profile.write_json("meta.json", meta)
    print(f"Reference library {'on' if meta['use_reference'] else 'off'} for {meta['name']}.")


def cmd_correct(args):
    learner.correct(_load(args.slug), args.context, args.bad, args.good)
    print("Correction saved.")


def cmd_approve(args):
    learner.approve(_load(args.slug), args.context, [s for s in args.reply.split(" | ") if s])
    print("Saved as a good reply.")


def cmd_screenshots(args):
    messages, engine = parse_screenshots(args.screenshots, them=args.them, me=args.me, engine=args.ocr)
    text = to_transcript(messages)
    if args.save:
        with open(args.save, "w", encoding="utf-8") as fh:
            fh.write(text)
        print(f"Wrote {len(messages)} bubbles to {args.save} ({engine} OCR). Fix any mistakes, then:")
        print(f"  python3 main.py create --file {args.save} --target \"{args.them}\" --me \"{args.me}\" --relationship ...")
    else:
        print(text, end="")
        print(f"\n({len(messages)} bubbles, {engine} OCR. Add --save chat.txt to edit before importing.)")


def _cleared(c: dict) -> str:
    parts = [f"{c['corrections']} correction(s)", f"{c['approved']} approval(s)", f"{c['notes']} note(s)"]
    return ", ".join(p for p, n in zip(parts, c.values()) if n) or "nothing"


def cmd_undo(args):
    profile = _load(args.slug)
    snap = learner.undo(profile)
    if not snap:
        sys.exit(f"Nothing to undo for {profile.meta['name']}.")
    print(f"Undid: {snap['label']} ({snap['at']}). {profile.meta['name']} is back to v{profile.meta.get('version')}.")
    left = len(profile.snapshots())
    print(f"{left} earlier change(s) can still be undone." if left else "That was the earliest change.")


def cmd_reset(args):
    profile = _load(args.slug)
    name = profile.meta["name"]
    if args.to_start:
        if not args.yes and input(f"Return {name} to how it was first created? This forgets every later change. [y/N] ").strip().lower() != "y":
            sys.exit("Cancelled.")
        snap = learner.reset_to_start(profile)
        print(f"{name} is back to how it was first created (v{profile.meta.get('version')})." if snap
              else f"{name} hasn't changed since it was created.")
        return
    cleared = learner.reset_feedback(profile)
    if any(cleared.values()):
        print(f"Cleared {_cleared(cleared)} for {name}. What it learned from your chats is kept.")
        print(f"Changed your mind? python3 main.py undo {profile.slug}")
    else:
        print(f"{name} has no corrections, approvals or notes to clear.")


def cmd_history(args):
    profile = _load(args.slug)
    snaps = profile.snapshots()
    if not snaps:
        print(f"No saved changes for {profile.meta['name']} yet.")
        return
    print(f"Changes to {profile.meta['name']} that can be undone, newest first:")
    for s in reversed(snaps):
        print(f"  {s.get('at', ''):19s}  v{s.get('version')}  {s.get('label', '')}")
    print(f"\npython3 main.py undo {profile.slug}   undoes the newest")


def _features_for(spec: str, args) -> tuple[str, dict]:
    """A profile slug, a sample id, or (with --file) an export, as (name, features)."""
    from tools.features import compute_features

    profile = Profile(spec)
    if profile.exists():
        m = profile.meta
        return m["name"], compute_features(profile.messages(), m["target"], m.get("me"), m.get("relationship"))
    samples = {s["id"]: s for s in _samples()}
    if spec in samples:
        s = samples[spec]
        msgs = parse_file(Path(__file__).resolve().parent / s["file"])
        return s["name"], compute_features(msgs, s["target"], s["me"], s["relationship"])
    known = ", ".join([p.slug for p in list_profiles()] + list(samples))
    sys.exit(f"'{spec}' is neither a profile nor a sample. Try one of: {known}")


def cmd_features(args):
    import csv as csvmod

    from tools.features import compute_features, flat_row, format_comparison, format_report

    named: list[tuple[str, dict]] = []
    if args.file:
        if not args.target:
            people = participants(parse_file(args.file))
            sys.exit("Say whose features to measure with --target. People in that file: "
                     + ", ".join(f"{n} ({c})" for n, c in people))
        msgs = parse_file(args.file)
        named.append((args.target, compute_features(msgs, args.target, args.me, args.relationship)))
    specs = list(args.who)
    if args.all_samples:
        specs += [s["id"] for s in _samples()]
    if args.all_profiles:
        specs += [p.slug for p in list_profiles()]
    named += [_features_for(s, args) for s in specs]
    if not named:
        sys.exit("Name a profile or sample (python3 main.py features dana), or use --file, --all-samples or --all-profiles.")

    if args.json:
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump({n: f for n, f in named}, fh, indent=2, ensure_ascii=False)
        print(f"Wrote {args.json}")
    if args.csv:
        rows = [flat_row(n, f) for n, f in named]
        cols = list(dict.fromkeys(k for r in rows for k in r))
        with open(args.csv, "w", encoding="utf-8", newline="") as fh:
            w = csvmod.DictWriter(fh, fieldnames=cols)
            w.writeheader()
            w.writerows(rows)
        print(f"Wrote {args.csv} ({len(rows)} row(s), {len(cols)} columns)")
    if args.json or args.csv:
        return
    if len(named) == 1:
        print(format_report(*named[0]))
    else:
        print(format_comparison(named))
        print("\nFull report for one: python3 main.py features <name>")


def cmd_list(_args):
    profiles = list_profiles()
    if not profiles:
        print("No profiles yet. Start with: python3 main.py create --file <chat export>")
    for p in profiles:
        m = p.meta
        print(f"{p.slug:20s} {m.get('name', ''):20s} {m.get('relationship', ''):12s} v{m.get('version')}  "
              f"{len(p.corrections())} corrections")


def cmd_show(args):
    profile = _load(args.slug)
    _print_rules(profile)
    if args.persona:
        print("\n" + profile.persona)


def _type_out(name: str, bubbles: list[str], style: dict, fast: bool) -> None:
    delay = min((style.get("them", {}).get("median_reply_seconds") or 2) / 30, 2.5)
    for bubble in bubbles:
        if not fast:
            time.sleep(delay * random.uniform(0.4, 1.0))
        print(f"  {name}: {bubble}")


def cmd_chat(args):
    profile = _load(args.slug)
    scratch = None
    if args.practice:
        # Work on a copy: corrections still shape this conversation, then vanish when you leave.
        scratch = Path(tempfile.mkdtemp(prefix="textback-practice-"))
        shutil.copytree(profile.dir, scratch / profile.slug, ignore=shutil.ignore_patterns("snapshots", "history"))
        profile = Profile(profile.slug, scratch)
    try:
        _chat_loop(profile, args)
    finally:
        if scratch:
            shutil.rmtree(scratch, ignore_errors=True)
            print("(practice mode: nothing was saved)")


def _chat_loop(profile, args):
    name = profile.meta["name"]
    mode = " (practice mode: nothing is saved)" if args.practice else ""
    print(f"Texting {name}{mode}. /help for commands.\n")
    history: list[dict] = []
    last_context, last_reply, last_why = "", [], ""
    while True:
        try:
            line = input("you > ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not line:
            continue
        cmd, _, rest = line.partition(" ")
        if cmd in ("/quit", "/exit"):
            break
        if cmd == "/help":
            print(CHAT_HELP)
        elif cmd == "/undo":
            snap = learner.undo(profile)
            print(f"  (undid: {snap['label']})" if snap else "  (nothing to undo)")
        elif cmd == "/forget":
            cleared = learner.reset_feedback(profile)
            print(f"  (cleared {_cleared(cleared)}; /undo brings them back)" if any(cleared.values()) else "  (nothing to reset)")
        elif cmd == "/why":
            print(f"  ({last_why or 'nothing to explain yet'})")
        elif cmd == "/style":
            _print_rules(profile)
        elif cmd == "/reset":
            history, last_context, last_reply, last_why = [], "", [], ""
            print("  (conversation cleared)")
        elif cmd == "/note" and rest:
            learner.add_note(profile, rest)
            print("  (noted, persona rebuilt)")
        elif cmd == "/good":
            if last_reply:
                learner.approve(profile, last_context, last_reply)
                print("  (saved as a good reply)")
        elif cmd == "/fix":
            if not last_reply or not rest:
                print("  usage: /fix <what they'd actually say>")
                continue
            good = [s.strip() for s in rest.split(" | ") if s.strip()]
            if not good:
                print("  usage: /fix <what they'd actually say>")
                continue
            learner.correct(profile, last_context, last_reply, good)
            # Swap the bad reply for the fixed one so the conversation continues correctly.
            history = [h for h in history if not (h["role"] == "them" and h["text"] in last_reply)]
            history += [{"role": "them", "text": g} for g in good]
            last_reply = good
            print("  (correction saved; they'll text like that next time)")
        elif cmd == "/nudge":
            result = generate_opener(profile, history)
            _type_out(name, result["replies"], profile.style, args.fast)
            history += [{"role": "them", "text": r} for r in result["replies"]]
            last_context, last_reply, last_why = "", result["replies"], result.get("explanation", "")
        else:
            result = generate_reply(profile, history, line)
            _type_out(name, result["replies"], profile.style, args.fast)
            history.append({"role": "me", "text": line})
            history += [{"role": "them", "text": r} for r in result["replies"]]
            last_context, last_reply, last_why = line, result["replies"], result.get("explanation", "")
            if args.explain:
                print(f"  (why: {last_why})")


def cmd_export(args):
    profile = _load(args.slug)
    out = args.out or f"{profile.slug}.textback.json"
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(profile.bundle(), fh, indent=2, ensure_ascii=False)
    print(f"Wrote {out}. Load it in the web view with 'Import'.")


def cmd_serve(args):
    from tools.server import serve

    serve(args.port)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="textback", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("participants", help="list senders in a chat export")
    s.add_argument("file")
    s.set_defaults(func=cmd_participants)

    s = sub.add_parser("create", help="learn a new person from a chat export or screenshots")
    s.add_argument("--file", help="chat export (.txt, .csv, .json)")
    s.add_argument("--sample", metavar="ID", help="use a built-in sample person (see: python3 main.py samples)")
    s.add_argument("--screenshots", nargs="+", metavar="PATH", help="screenshot images and/or folders of them")
    s.add_argument("--ocr", default="auto", choices=["auto", "vision", "tesseract"],
                   help="how to read screenshots (auto picks the best available)")
    s.add_argument("--target", help="their sender name in the export")
    s.add_argument("--me", help="your sender name in the export")
    s.add_argument("--name", help="display name (defaults to --target)")
    s.add_argument("--relationship", default="friend", type=relationship,
                   help=f"one of: {', '.join(RELATIONSHIPS)} (use quotes or a dash: talking-stage)")
    s.add_argument("--notes", help="things the chat won't show")
    s.add_argument("--no-reference", action="store_true", help="don't fall back on the built-in reference library")
    s.set_defaults(func=cmd_create)

    s = sub.add_parser("learn", help="feed a newer export or more screenshots into an existing profile")
    s.add_argument("slug")
    s.add_argument("--file")
    s.add_argument("--screenshots", nargs="+", metavar="PATH")
    s.add_argument("--ocr", default="auto", choices=["auto", "vision", "tesseract"])
    s.set_defaults(func=cmd_learn)

    s = sub.add_parser("note", help="teach a fact or habit")
    s.add_argument("slug")
    s.add_argument("fact")
    s.set_defaults(func=cmd_note)

    s = sub.add_parser("reference", help="turn the built-in reference library on/off for one person")
    s.add_argument("slug")
    s.add_argument("state", choices=["on", "off"])
    s.set_defaults(func=cmd_reference)

    s = sub.add_parser("correct", help="save 'they would say X instead'")
    s.add_argument("slug")
    s.add_argument("--context", required=True, help="what you texted")
    s.add_argument("--bad", required=True, help="the reply that sounded wrong")
    s.add_argument("--good", required=True, help="what they'd really say (' | ' between bubbles)")
    s.set_defaults(func=cmd_correct)

    s = sub.add_parser("approve", help="save a reply as spot-on")
    s.add_argument("slug")
    s.add_argument("--context", required=True)
    s.add_argument("--reply", required=True)
    s.set_defaults(func=cmd_approve)

    s = sub.add_parser("chat", help="text with someone in the terminal")
    s.add_argument("slug")
    s.add_argument("--fast", action="store_true", help="skip the typing delay")
    s.add_argument("--explain", action="store_true", help="print why each reply was chosen")
    s.add_argument("--practice", action="store_true", help="practice mode: corrections only last for this chat")
    s.set_defaults(func=cmd_chat)

    s = sub.add_parser("screenshots", help="read screenshots into an editable transcript (no profile changes)")
    s.add_argument("screenshots", nargs="+", metavar="PATH")
    s.add_argument("--them", default="Them", help="name for the left-side bubbles")
    s.add_argument("--me", default="Me", help="name for the right-side bubbles")
    s.add_argument("--ocr", default="auto", choices=["auto", "vision", "tesseract"])
    s.add_argument("--save", help="write 'Name: text' lines to this file")
    s.set_defaults(func=cmd_screenshots)

    s = sub.add_parser("undo", help="undo the last change to a person (learn, correction, approval, note, reset)")
    s.add_argument("slug")
    s.set_defaults(func=cmd_undo)

    s = sub.add_parser("reset", help="forget your corrections, approvals and notes (or --to-start)")
    s.add_argument("slug")
    s.add_argument("--to-start", action="store_true", help="go back to how the profile was first created")
    s.add_argument("--yes", "-y", action="store_true", help="don't ask for confirmation")
    s.set_defaults(func=cmd_reset)

    s = sub.add_parser("history", help="list the changes that can be undone")
    s.add_argument("slug")
    s.set_defaults(func=cmd_history)

    sub.add_parser("samples", help="list the built-in sample people").set_defaults(func=cmd_samples)

    s = sub.add_parser("features", help="analyse texting features (one person, a comparison, or a CSV/JSON export)")
    s.add_argument("who", nargs="*", help="profile slugs and/or sample ids")
    s.add_argument("--file", help="analyse a chat export directly, without creating a profile")
    s.add_argument("--target", help="with --file: whose side is 'them'")
    s.add_argument("--me", help="with --file: your sender name")
    s.add_argument("--relationship", type=relationship, default="other", help="with --file: for reading kinds of text")
    s.add_argument("--all-samples", action="store_true", help="include every sample person")
    s.add_argument("--all-profiles", action="store_true", help="include every saved profile")
    s.add_argument("--csv", help="write one row per person to this CSV file")
    s.add_argument("--json", help="write the full features to this JSON file")
    s.set_defaults(func=cmd_features)

    sub.add_parser("list", help="list profiles").set_defaults(func=cmd_list)

    s = sub.add_parser("show", help="show someone's style rules")
    s.add_argument("slug")
    s.add_argument("--persona", action="store_true")
    s.set_defaults(func=cmd_show)

    s = sub.add_parser("export", help="export a profile bundle for the web view")
    s.add_argument("slug")
    s.add_argument("--out")
    s.set_defaults(func=cmd_export)

    s = sub.add_parser("serve", help="run the web view on localhost")
    s.add_argument("--port", type=int, default=8765)
    s.set_defaults(func=cmd_serve)
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        args.func(args)
    except (FileNotFoundError, ValueError, RuntimeError) as exc:
        sys.exit(f"error: {exc}")


if __name__ == "__main__":
    main()
