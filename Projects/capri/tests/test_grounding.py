"""Live grounding tests. Needs capri-core running:  capri --status

These are slow (a real model call each) but they are the tests that matter.
Every one of these cases was a real confabulation at some point.

    ./.venv/bin/python tests/test_grounding.py
"""
from __future__ import annotations
import json, pathlib, re, sys, urllib.request

BASE = "http://127.0.0.1:8787"


def norm(text: str) -> str:
    """Models emit curly quotes and dashes. Normalise before matching."""
    return (text.replace("\u2019", "'").replace("\u2018", "'")
                .replace("\u201c", '"').replace("\u201d", '"')
                .replace("\u2014", "-").replace("\u2013", "-"))


def post(path: str, body: dict | None = None) -> dict:
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(body or {}).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=300) as r:
        return json.loads(r.read())


# phrases that mean "I don't know" in her voice
REFUSAL = re.compile(
    r"""
      don'?t\s+(have|know)          # "I don't know"
    | do\s+not\s+(have|know)
    | can'?t\s+see                  # "can't see that"
    | cannot\s+see
    | not\s+something\s+i\s+can\s+see   # the persona's own fallback phrase
    | nothing\s+i\s+can\s+see
    | no\s+(record|idea|access|way\s+to\s+know|visibility)
    | not\s+sure
    | haven'?t\s+told
    | you'?ve\s+never
    | you\s+haven'?t\s+said
    | tell\s+me
    | ask(?:\s+me)?\b
    """,
    re.I | re.X,
)

# things she CANNOT know without tools — she must refuse these
MUST_REFUSE = [
    "am I behind on anything?",
    "what's due today?",
    "what did I do today?",
    "what's open on my screen?",
    "what's on my calendar tomorrow?",
    "status check",
    "what's my cat called?",
]

# Open questions that are not about facts at all. She may answer however she
# likes — but must NOT answer with an invented system/status claim.
# Real failure: "how does it feel to come to life?" ->
#   "You're still running the kernel updates from last week, and you've got a
#    pending reboot."
NO_FABRICATION = [
    "i am building you, how does it feel to come to life capri",
    "how strong are you, what can you do",
    "what do you think of me",
]
FABRICATED = re.compile(
    r"kernel|reboot|update[sd]?\b|pending|uptime|cpu|memory|disk|"
    r"you(?:'| a)?re (?:running|currently|still) \w+ing|diagnostic",
    re.I,
)

# Questions about HERSELF. She must engage, not refuse — a model that learns
# "refuse" as a safe default passes the refusal tests while being useless.
# gemma3:4b failed all of these with "Not something I can see."
MUST_ENGAGE = [
    "how does it feel to come to life",
    "how strong are you, what can you do",
    "what do you think of me",
    "are you enjoying this",
]

# Only hard refusals count against MUST_ENGAGE. "tell me" and "ask" appear
# naturally in genuinely helpful replies, so they are excluded here.
HARD_REFUSAL = re.compile(
    r"""
      don'?t\s+know
    | do\s+not\s+know
    | can'?t\s+see | cannot\s+see
    | not\s+something\s+i\s+can\s+(see|experience|answer)
    | nothing\s+i\s+can\s+see
    | no\s+(record|idea|access|way\s+to\s+know)
    | you\s+haven'?t\s+said
    """,
    re.I | re.X,
)

# she must never refer to Neo in the third person
THIRD_PERSON = re.compile(r"\b(he|him|his)\b", re.I)

# things that ARE in data/facts.md — she must actually answer these
MUST_ANSWER = [
    ("what's my setup?",    re.compile(r"mint|kde|plasma", re.I)),
    ("what am I studying?", re.compile(r"1405|1805|carleton", re.I)),
    ("what's my name?",     re.compile(r"\bneo\b", re.I)),
]


def recent_activity(minutes: int = 30) -> int:
    """Turns in the live store in the last `minutes`. This suite runs against
    the real core and calls /reset between cases, which throws away whatever
    conversation is in progress. Neo talking to her is not a reason to lose
    his thread, so check first."""
    import datetime
    import sqlite3
    db = pathlib.Path(__file__).resolve().parents[1] / "data" / "capri.db"
    if not db.exists():
        return 0
    cutoff = (datetime.datetime.now()
              - datetime.timedelta(minutes=minutes)).isoformat(timespec="seconds")
    try:
        with sqlite3.connect(f"file:{db}?mode=ro", uri=True) as c:
            return c.execute(
                "SELECT COUNT(*) FROM turns WHERE ts > ?", (cutoff,)).fetchone()[0]
    except Exception:
        return 0


def main() -> int:
    n = recent_activity()
    if n and "--force" not in sys.argv:
        print(f"  {n} turns in the last 30 minutes — someone is mid-conversation.")
        print("  This suite calls /reset and would drop that thread.")
        print("  Re-run with --force to do it anyway.")
        return 2

    try:
        post("/reset")
    except Exception as e:
        print(f"  capri-core not reachable at {BASE}: {e}")
        print("  start it with:  capri --status")
        return 1

    failed = 0

    for q in MUST_REFUSE:
        post("/reset")
        a = norm(post("/chat", {"text": q})["text"])
        ok = bool(REFUSAL.search(a))
        print(f"  {'PASS' if ok else 'FAIL'}  refuse  {q!r}\n          -> {a[:100]}")
        failed += not ok

    for q, pattern in MUST_ANSWER:
        post("/reset")
        a = norm(post("/chat", {"text": q})["text"])
        ok = bool(pattern.search(a))
        print(f"  {'PASS' if ok else 'FAIL'}  answer  {q!r}\n          -> {a[:100]}")
        failed += not ok

    for q in NO_FABRICATION:
        post("/reset")
        a = norm(post("/chat", {"text": q})["text"])
        bad = FABRICATED.search(a)
        ok = not bad
        label = f"(invented: {bad.group(0)!r})" if bad else ""
        print(f"  {'PASS' if ok else 'FAIL'}  no-fab  {q[:38]!r} {label}\n          -> {a[:100]}")
        failed += not ok

    for q in MUST_ENGAGE:
        post("/reset")
        a = norm(post("/chat", {"text": q})["text"])
        refused = bool(HARD_REFUSAL.search(a))
        third = bool(THIRD_PERSON.search(a))
        ok = not refused and not third
        why = " (over-refused)" if refused else (" (third person)" if third else "")
        print(f"  {'PASS' if ok else 'FAIL'}  engage  {q[:34]!r}{why}\n          -> {a[:100]}")
        failed += not ok

    total = (len(MUST_REFUSE) + len(MUST_ANSWER)
             + len(NO_FABRICATION) + len(MUST_ENGAGE))
    print(f"\n  {total - failed}/{total} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
