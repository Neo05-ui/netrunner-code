"""Delivery commands she understands in conversation, handled in code.

Why these bypass the model entirely, like `remember` and `forget` before
them: "shut up" must work. A 3B model asked to silence itself will sometimes
agree warmly and do nothing, and the one command that must never be
paraphrased is the one that makes the interruptions stop.

Nothing here talks to the daemon. The kill switch is a file and the ledger is
SQLite, both of which the daemon re-reads on its next cycle - so this works
whether the daemon is running, starting, wedged, or not installed. The chat
path and the terminal path are the same two pieces of state.
"""
from __future__ import annotations

import random
import re
from datetime import datetime, timedelta

from .killswitch import parse_duration

# "shut up", "be quiet for 2 hours", "mute yourself", "stop reminding me",
# "/quiet 30m". Deliberately narrow: this fires on a sentence that is ONLY an
# instruction to go quiet, so a conversation about silence is not one.
HUSH = re.compile(
    r"^\s*(?:/quiet|/mute|/hush"
    r"|(?:please\s+)?(?:shut up|be quiet|go quiet|mute yourself|hush"
    r"|stop (?:reminding|nagging|bugging|notifying)(?:\s+me)?"
    r"|no more (?:reminders?|notifications?|popups?)))"
    r"(?:\s+for)?\s*(\d+\s*[a-z]*)?\s*[.!]?\s*$", re.I)

UNHUSH = re.compile(
    r"^\s*(?:/quiet\s+off|/unmute"
    r"|(?:you can\s+)?(?:unmute|speak|talk|remind me)(?:\s+again)?"
    r"|reminders? (?:back )?on"
    r"|start (?:reminding|notifying)(?:\s+me)?(?:\s+again)?)\s*[.!]?\s*$", re.I)

# "done with the assignment", "/ack midterm", "I finished the lab report"
ACK = re.compile(
    r"^\s*(?:/ack|(?:i\s*(?:'m|am)?\s+)?(?:done|finished|completed)\s+(?:with\s+)?"
    r"|(?:i\s+)?(?:did|handed in|submitted)\s+)(.+?)\s*[.!]?\s*$", re.I)

# "what are you reminding me about", "/reminders"
LIST = re.compile(
    r"^\s*(?:/reminders?"
    r"|what (?:are you|have you been) (?:reminding|nagging|bugging) me about"
    r"|what(?:'s| is) (?:on )?your (?:list|ledger))\s*\??\s*$", re.I)

HUSHED = ["Fine. Quiet.", "Alright, I'll shut up.", "Muted.", "Going quiet."]
UNHUSHED = ["Back on.", "Alright, I'm listening again.", "Unmuted."]


def parse(text: str):
    """Return (kind, payload) or None. Checked BEFORE the ack pattern, because
    "done" and "stop reminding me" would otherwise fight over the same line."""
    t = (text or "").strip()
    if not t:
        return None
    if UNHUSH.match(t):
        return ("unhush", "")
    m = HUSH.match(t)
    if m:
        return ("hush", (m.group(1) or "").replace(" ", ""))
    if LIST.match(t):
        return ("reminders", "")
    m = ACK.match(t)
    if m and len(m.group(1).strip()) >= 3:
        return ("ack", m.group(1).strip())
    return None


def handle(kind: str, payload: str, silence, ledger) -> str | None:
    """`silence` is a Silence, `ledger` a Ledger. Both file-backed, so this
    needs no running daemon and cannot be left out of sync with one.

    Returns None to mean NOT A COMMAND AFTER ALL - hand it to the model.
    That exists for one case and it matters: "I'm done with this week" is
    him venting, and the pattern for "done with <task>" cannot tell the
    difference. So an ack that matches nothing in the ledger is not an ack.
    Answering a bad day with "I haven't reminded you about anything
    matching this week" is the exact failure the disclosure handling in
    orchestrator.turn() was built to stop, and it is not worth
    reintroducing through a side door.
    """
    try:
        if kind == "hush":
            dur = parse_duration(payload) if payload else None
            if dur is None:
                silence.engage(None, "he told me to shut up")
                return (f"{random.choice(HUSHED)} Nothing until you tell me "
                        f"otherwise.")
            until = datetime.now() + dur
            silence.engage(until, f"he told me to shut up for {payload}")
            return f"{random.choice(HUSHED)} Back at {until:%H:%M}."

        if kind == "unhush":
            return (random.choice(UNHUSHED) if silence.release()
                    else "I wasn't muted.")

        if kind == "ack":
            rows = ledger.find(payload)
            if not rows:
                return None          # not about a reminder; let her answer
            if len(rows) > 1:
                titles = ", ".join(f"“{r.title}”" for r in rows[:4])
                return f"Which one — {titles}?"
            ledger.ack(rows[0].task_id, source="chat")
            return f"Noted, dropping “{rows[0].title}”."

        if kind == "reminders":
            rows = ledger.all()
            if not rows:
                return "Nothing. I haven't had to chase you about anything."
            now = datetime.now()
            lines = []
            for r in rows:
                state = ("done" if r.acked_at else
                         "snoozed" if r.snooze_until and r.snooze_until > now
                         else f"{r.sends}×, still open")
                lines.append(f"- T{r.tier} {r.title} ({state})")
            silent, why = silence.state(now)
            head = f"Muted — {why}.\n" if silent else ""
            return head + "\n".join(lines)
    except Exception as e:                      # noqa: BLE001
        # the one command that must never fail is the one that makes it stop
        if kind == "hush":
            return (f"Couldn't write the switch ({e!r}). Run `touch "
                    f"data/SILENCE` and I'll stop on my next cycle.")
        return f"That didn't work: {e!r}"
    return ""
