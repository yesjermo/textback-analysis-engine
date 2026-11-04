"""Tiny local server: serves web/ and a JSON API over your profiles. Standard library only.

GET  /api/status                -> {"engine": "offline", "profiles": n}
GET  /api/profiles              -> [{slug, name, relationship, version}]
GET  /api/profiles/<slug>       -> profile bundle (no raw chat log)
GET  /api/features/<slug>       -> texting features for both sides (tools/features.py)
POST /api/reply    {slug, history, message}
POST /api/nudge    {slug, history}
POST /api/correct  {slug, context, bad, good}
POST /api/approve  {slug, context, reply}
POST /api/undo     {slug}                -> {ok, undone: label | null}
POST /api/reset    {slug, to_start?}     -> {ok, cleared | restored}

Binds to 127.0.0.1 only: your chats never leave your machine through this server.
"""
from __future__ import annotations

import json
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import learner
from .profile_store import REPO_ROOT, Profile, list_profiles
from .reply_engine import generate_opener, generate_reply

WEB_DIR = REPO_ROOT / "web"
MAX_BODY = 2 * 1024 * 1024


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(WEB_DIR), **kwargs)

    def end_headers(self):
        self.send_header("Cache-Control", "no-cache")  # always serve the latest web/ files
        super().end_headers()

    def log_message(self, fmt, *args):  # keep the terminal quiet except for API calls
        if "/api/" in (args[0] if args else ""):
            super().log_message(fmt, *args)

    def _send(self, code: int, payload) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _profile(self, slug: str) -> Profile | None:
        p = Profile(slug)
        return p if p.exists() else None

    def do_GET(self):
        path = self.path.split("?")[0]
        if not path.startswith("/api/"):
            return super().do_GET()
        if path == "/api/status":
            return self._send(200, {"engine": "offline",
                                    "profiles": len(list_profiles())})
        if path == "/api/profiles":
            return self._send(200, [
                {"slug": p.slug, "name": p.meta.get("name"), "relationship": p.meta.get("relationship"),
                 "version": p.meta.get("version")} for p in list_profiles()
            ])
        if path.startswith("/api/features/"):
            from .features import compute_features

            profile = self._profile(path.rsplit("/", 1)[-1])
            if not profile:
                return self._send(404, {"error": "no such profile"})
            m = profile.meta
            return self._send(200, compute_features(profile.messages(), m["target"], m.get("me"), m.get("relationship")))
        if path.startswith("/api/profiles/"):
            profile = self._profile(path.rsplit("/", 1)[-1])
            return self._send(200, profile.bundle()) if profile else self._send(404, {"error": "no such profile"})
        return self._send(404, {"error": "not found"})

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_BODY:
            return self._send(413, {"error": "request too large"})
        try:
            data = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            return self._send(400, {"error": "invalid JSON"})
        profile = self._profile(str(data.get("slug", "")))
        if not profile:
            return self._send(404, {"error": "no such profile"})
        history = data.get("history") or []
        path = self.path.split("?")[0]
        if path == "/api/reply":
            return self._send(200, generate_reply(profile, history, str(data.get("message", ""))))
        if path == "/api/nudge":
            return self._send(200, generate_opener(profile, history))
        if path == "/api/correct":
            learner.correct(profile, data.get("context", ""), data.get("bad", []), data.get("good", []))
            return self._send(200, {"ok": True})
        if path == "/api/approve":
            learner.approve(profile, data.get("context", ""), data.get("reply", []))
            return self._send(200, {"ok": True})
        if path == "/api/undo":
            snap = learner.undo(profile)
            return self._send(200, {"ok": True, "undone": snap["label"] if snap else None, "bundle": profile.bundle()})
        if path == "/api/reset":
            if data.get("to_start"):
                snap = learner.reset_to_start(profile)
                return self._send(200, {"ok": True, "restored": bool(snap), "bundle": profile.bundle()})
            cleared = learner.reset_feedback(profile)
            return self._send(200, {"ok": True, "cleared": cleared, "bundle": profile.bundle()})
        return self._send(404, {"error": "not found"})


def serve(port: int = 8765, host: str = "127.0.0.1") -> None:
    server = ThreadingHTTPServer((host, port), Handler)
    print(f"TextBack web view: http://{host}:{port}  (Ctrl+C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nbye")
    finally:
        server.server_close()


if __name__ == "__main__":
    serve()
