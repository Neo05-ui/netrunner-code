"""The Blackwall: decides what may leave this machine, and what may not.

From Neo's routing spec. Three zones:

  RED    personal - feelings, relationships, health, money, identity, venting.
         100% local. Never leaves the machine, for any reason.
  AMBER  a technical task wrapped in personal context. The task may go out
         only after the personal part is stripped off.
  GREEN  purely technical. Nothing personal present, safe to send.

Two rules govern everything here:

1. FAIL CLOSED. Any doubt, any error, any unparseable classifier output, any
   empty input - the answer is RED. The cost of a wrong RED is a slower
   answer. The cost of a wrong GREEN is Neo's private life on someone else's
   server, permanently. Those are not comparable, so the tie never goes to
   the cloud.

2. RULES BEFORE MODEL. A regex that fires is certain; a model that classifies
   is probabilistic. Deterministic RED markers are checked first and are not
   overridable by the model. The model can only ever move something *down*
   from GREEN toward RED, never up toward the cloud.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum


class Zone(str, Enum):
    RED = "red"
    AMBER = "amber"
    GREEN = "green"


# Personal markers. Deliberately broad: a false RED costs latency, a false
# GREEN costs privacy. Ordered roughly by how unambiguous they are.
RED_PATTERNS = [
    # relationships and people
    r"\b(girlfriend|boyfriend|partner|ex|wife|husband|crush|dating|breakup|broke up)\b",
    r"\b(mum|mom|mother|dad|father|parents|sister|brother|family|friend)\b",
    # feelings and mental state
    r"\b(feel|feeling|felt|lonely|depress\w*|anxious|anxiety|scared|afraid"
    r"|sad|miserable|hurt|crying|cried|angry|upset|ashamed|guilt\w*"
    r"|overwhelmed|burnt? out|exhausted|hopeless|worthless)\b",
    r"\b(therapy|therapist|counsel\w+|medication|diagnos\w+|mental health)\b",
    # How people actually phrase distress. A plain "rough week" line contains
    # none of the words above, so it was classified as ordinary text until
    # this was added - which also meant the assistant deflected it as though
    # it were a request for data.
    r"\b(rough|tough|hard|bad|shit+y?|awful|terrible|long)\s+"
    r"(day|week|month|year|time|patch|one)\b",
    r"\b(struggling|not doing (great|well|ok)|barely|can'?t cope|fed up"
    r"|over it|falling apart|at my limit|need a break|done with it)\b",
    # health and body
    r"\b(doctor|hospital|symptom|illness|sick|pain|sleep|insomnia|weight)\b",
    # money
    r"\b(salary|rent|debt|loan|broke|afford|bank|savings|tuition|overdraft)\b",
    # identity and private reflection
    r"\b(i'?m scared|i'?m worried|i hate myself|move on from|miss (her|him|them)"
    r"|my life|my future|who i am|journal|vent(ing)?)\b",
]
RED_RE = [re.compile(p, re.I) for p in RED_PATTERNS]

# Absolute RED. These can never be AMBER, because AMBER means "send the
# technical part" - and for a credential the secret IS the technical part.
# Caught by the first test run: "my api key is sk-abc123" classified AMBER
# because "api" read as a technical marker, which would have shipped the key.
ABSOLUTE_RED_PATTERNS = [
    r"\b(password|passphrase|api[_ ]?key|access[_ ]?token|bearer|secret"
    r"|private key|credential|ssh key|\.pem\b|seed phrase)\b",
    r"\bsk-[A-Za-z0-9]{8,}",          # OpenAI-style key
    r"\bgh[pousr]_[A-Za-z0-9]{16,}",  # GitHub token
    r"\bAKIA[0-9A-Z]{12,}",           # AWS key id
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
]
ABSOLUTE_RED_RE = [re.compile(p, re.I) for p in ABSOLUTE_RED_PATTERNS]

# Technical markers. Presence does NOT make something green on its own - it
# only distinguishes AMBER (personal + technical) from RED (personal alone).
TECH_PATTERNS = [
    r"\b(code|script|function|class|bug|error|traceback|compile|debug"
    r"|python|javascript|rust|java|sql|regex|api|json|yaml|html|css"
    r"|algorithm|complexity|proof|theorem|integral|derivative|matrix"
    r"|install|package|docker|git|linux|kernel|server|database"
    r"|hash ?map|hash ?table|array|linked list|binary tree|graph|stack|queue"
    r"|pointer|recursion|collision|sort(ing)?|search|big-?o|runtime"
    r"|variable|loop|syntax|library|framework|compiler|thread|cache)\b",
    r"\b(write|build|make|fix|explain|implement|refactor|optimi[sz]e)\b"
    r".{0,40}\b(script|program|code|function|query|command)\b",
]
TECH_RE = [re.compile(p, re.I) for p in TECH_PATTERNS]


@dataclass
class Verdict:
    zone: Zone
    reason: str
    matched: list[str]          # which markers fired, for the audit log

    @property
    def may_leave_machine(self) -> bool:
        return self.zone is Zone.GREEN

    @property
    def needs_sanitising(self) -> bool:
        return self.zone is Zone.AMBER


def classify(text: str) -> Verdict:
    """Rules-only classification. Never raises; anything odd is RED."""
    try:
        if not text or not text.strip():
            return Verdict(Zone.RED, "empty input", [])

        absolute = [r.pattern[:38] for r in ABSOLUTE_RED_RE if r.search(text)]
        if absolute:
            # no downgrade path, not even to AMBER
            return Verdict(Zone.RED, "credential or secret present", absolute)

        hits = [r.pattern[:38] for r in RED_RE if r.search(text)]
        tech = any(r.search(text) for r in TECH_RE)

        if hits and tech:
            return Verdict(Zone.AMBER, "personal context around a technical task", hits)
        if hits:
            return Verdict(Zone.RED, "personal content", hits)
        if tech:
            return Verdict(Zone.GREEN, "technical, no personal markers", [])

        # Nothing matched either way. This is the case that decides the whole
        # design: an unclassifiable sentence is not evidence of safety.
        return Verdict(Zone.RED, "unclassified - defaulting local", [])
    except Exception as e:                      # noqa: BLE001
        return Verdict(Zone.RED, f"classifier error, defaulting local: {e!r}", [])
