"""Memory commands intercepted before the model.

"remember that ..." and "forget ..." are handled in code, not by the brain.
Two reasons: a 8B model asked to update a file will sometimes agree and do
nothing, and a write to durable memory should be exact rather than paraphrased.
The reply still sounds like her, it just isn't generated.
"""
from __future__ import annotations

import random
import re

# "remember that X", "remember: X", "remember X", "note that X", "keep in mind X"
REMEMBER = re.compile(
    r"^\s*(?:please\s+)?(?:remember|note|keep in mind|don'?t forget)\b"
    r"\s*(?:that|this|:)?\s*(.+)$", re.I | re.S)

# "forget X", "forget that X", "forget about X", "delete the fact that X"
FORGET = re.compile(
    r"^\s*(?:please\s+)?(?:forget|drop|delete|remove)\b"
    r"\s*(?:that|this|about|the fact that|the fact)?\s*(.+)$", re.I | re.S)

# "what do you know about me", "what do you remember", "list facts"
LIST = re.compile(
    r"^\s*(?:what do you (?:know|remember)(?:\s+about\s+me)?"
    r"|list (?:your )?facts|show (?:me )?(?:your )?(?:facts|memory))\s*\??\s*$", re.I)

STORED = ["Noted.", "Got it.", "Filed.", "Stored.", "Fine, noted."]
DROPPED = ["Gone.", "Dropped it.", "Forgotten.", "Wiped."]


def parse(text: str):
    """Return (kind, payload) or None. kind in {remember, forget, list}."""
    t = text.strip()
    if LIST.match(t):
        return ("list", "")
    m = REMEMBER.match(t)
    if m and m.group(1).strip():
        return ("remember", m.group(1).strip())
    m = FORGET.match(t)
    if m and m.group(1).strip():
        return ("forget", m.group(1).strip())
    return None


def handle(kind: str, payload: str, facts, store=None) -> str:
    if kind == "list":
        bullets = facts.bullets()
        if not bullets:
            return "Nothing yet. Tell me something."
        return "\n".join(f"- {b}" for b in bullets)

    if kind == "remember":
        return (f"{random.choice(STORED)} “{payload.rstrip('.')}”"
                if facts.add(payload) else "Already knew that.")

    if kind == "forget":
        gone = facts.remove(payload)
        if gone:
            return f"{random.choice(DROPPED)} “{gone.rstrip('.')}”"
        return "Nothing stored that matches. Say it closer to how I have it."

    return ""
