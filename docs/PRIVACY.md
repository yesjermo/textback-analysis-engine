# Privacy and responsible use

Chat logs are personal, and they involve someone who didn't sign up for this. TextBack is
built to keep that data close.

## Where your data goes

| Mode | Where chats and profiles live | What leaves your machine |
|---|---|---|
| CLI or server | `profiles/` on your disk | nothing |
| `main.py serve` | `profiles/` on your disk | nothing (the server binds to 127.0.0.1) |
| Static web view | this browser's localStorage | nothing (reading screenshots downloads the Tesseract.js reader; your images stay in the browser) |
| Screenshots with `--ocr vision` / `tesseract` | `profiles/` on your disk | nothing |

`profiles/`, `.env` and exported bundles are gitignored, so they won't end up in your repo by accident.

## Ground rules

1. **Only your own conversations.** Import chats you were part of.
2. **Practice, not impersonation.** Don't send generated texts to anyone while posing as the real person,
   and don't use a profile to deceive, harass or manipulate anyone.
3. **No sensitive inventions.** Do not make up health, money, address or other private facts about the person.
4. **Screenshots show other people too.** Group chats, names and photos in a screenshot belong to other people.
   Crop to the one conversation you mean to learn from.
5. **Exes and talking stages.** A profile of an ex or someone you're getting to know is for rehearsing what to
   say or working through how you feel. Don't use it to keep contacting someone who has asked for space, and
   don't treat its guesses about their feelings as facts.
6. **Undo keeps copies.** Each change saves a copy of the profile in `profiles/<slug>/snapshots/` (up to 20, the
   first always kept) so it can be undone. `reset --to-start` deletes them; so does deleting the profile.
7. **Delete on request.** `rm -rf profiles/<slug>` removes everything about that person. In the web view,
   use **Remove**.
8. **Workplace chats** may be covered by your employer's policies. Check them before exporting work chats.
