"""Neo's Interrupt Priority Matrix, as code.

  TIER 0  CRITICAL OVERLOAD  exams, assignment deadlines, lab submissions
  TIER 1  ACTIVE DIRECTIVE   workouts, habits, project milestones, meetings
  TIER 2  SUB-ROUTINE        calls, shopping, chores, errands
  TIER 3  DOPAMINE DROP      anime, game drops, music gear, lore

Three signals, in order of trust:
  1. an explicit keyword in the task title     (strongest)
  2. TickTick's own priority flag              (he set it deliberately)
  3. how close the due date is                 (escalates, never de-escalates)

Due-date proximity can only raise a tier, and never into TIER 0. Only a task
whose own title says exam/assignment/deadline is allowed to be CRITICAL -
otherwise a workout due in two hours becomes a screaming emergency, which is
exactly what happened the first time this ran.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

TIER_NAMES = {0: "CRITICAL OVERLOAD", 1: "ACTIVE DIRECTIVE",
              2: "SUB-ROUTINE", 3: "DOPAMINE DROP"}

# Plurals matter. "assignment" with a trailing \b does not match
# "Assignments", which is how half of Neo's real list is written - the first
# run against his actual tasks filed them as unclassified.
KEYWORDS = {
    0: r"\b(exams?|finals?|midterms?|assignments?|submissions?|submit"
       r"|deadlines?|labs?|quiz(zes)?|tests?|defen[cs]es?|vivas?|thesis"
       r"|applications?|interviews?)\b",
    1: r"\b(workouts?|gym|runs?|training|study(ing)?|revise|revisions?"
       r"|sprints?|milestones?|meetings?|standups?|lectures?|tutorials?"
       r"|practice|habits?|reviews?|notes?|derivations?|problems?|readings?)\b",
    2: r"\b(calls?|emails?|repl(y|ies)|buy|groceries|shopping|clean(ing)?"
       r"|laundry|tidy|bins?|renew|books?|appointments?|pay|collect|post"
       r"|errands?|refill)\b",
    3: r"\b(anime|episodes?|genshin|banners?|games?|releases?|drops?|albums?"
       r"|lore|watch(ing)?|streams?|manga|gacha|patch(es)?|dlc|yt|youtube)\b",
}
KEYWORD_RE = {t: re.compile(p, re.I) for t, p in KEYWORDS.items()}

# TickTick: 0 none, 1 low, 3 medium, 5 high.
# Priority 0 means "not set", which is not evidence of triviality - it maps to
# the boring middle, not to DOPAMINE. Caught in testing: an unrecognised task
# with no priority was being filed as entertainment.
TICKTICK_PRIORITY_TIER = {5: 0, 3: 1, 1: 2, 0: 2}


def _parse_due(value: str | None) -> datetime | None:
    if not value:
        return None
    v = value.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(v)
    except ValueError:
        try:
            dt = datetime.strptime(value[:19], "%Y-%m-%dT%H:%M:%S")
        except ValueError:
            return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


# A task's project says a lot that its title does not. "Videos" in a course
# project is coursework; "Games" in a personal one is not. Discovered on the
# first run against the real list, where both were landing in the same tier.
ACADEMIC_PROJECT = re.compile(
    r"comp|calc|discrete|philosoph|math|physic|chem|bio|stat|structure"
    r"|course|uni|school|study|cs\d|intro to", re.I)
LEISURE_PROJECT = re.compile(r"personal|home|life|fun|game|media|watch", re.I)

STALE_AFTER = timedelta(days=14)


def classify(title: str, *, priority: int = 0, due: str | None = None,
             now: datetime | None = None, project: str = "") -> tuple[int, str]:
    """Return (tier, why). Never raises — an unclassifiable task is TIER 2,
    the boring middle, so a bad parse cannot invent an emergency."""
    try:
        title = title or ""
        tier, why = None, ""

        for t in (0, 1, 2, 3):                 # most urgent keyword wins
            if KEYWORD_RE[t].search(title):
                tier, why = t, f"title matches {TIER_NAMES[t].lower()}"
                break

        # "Yt videos" filed under a course is lecture material, not leisure.
        # A DOPAMINE keyword inside an academic project loses to the project.
        if tier == 3 and project and ACADEMIC_PROJECT.search(project):
            tier, why = 1, f"media keyword, but academic project ({project})"

        if tier is None:
            # no keyword: let the project decide before falling back to the
            # priority flag, which Neo mostly leaves unset
            if project and ACADEMIC_PROJECT.search(project):
                tier, why = 1, f"no keyword; academic project ({project})"
            elif project and LEISURE_PROJECT.search(project):
                tier, why = 3, f"no keyword; leisure project ({project})"
            else:
                tier = TICKTICK_PRIORITY_TIER.get(priority, 2)
                why = f"no keyword; TickTick priority {priority}"

        critical_by_title = bool(KEYWORD_RE[0].search(title))
        floor = 0 if critical_by_title else 1      # only titles earn TIER 0

        d = _parse_due(due)
        if d is not None and tier > floor and tier < 3:
            # TIER 3 never escalates: an overdue anime episode is not a
            # deadline, and Neo's whole list being weeks old would otherwise
            # promote every leisure item into his face.
            left = d - (now or datetime.now(timezone.utc))
            hours = left.total_seconds() / 3600
            if -STALE_AFTER <= left < timedelta(0):
                tier, why = max(floor, tier - 1), why + "; overdue"
            elif left < -STALE_AFTER:
                why += f"; STALE ({abs(left).days}d overdue, not escalated)"
            elif left <= timedelta(hours=24):
                tier, why = max(floor, tier - 1), why + f"; due in {hours:.0f}h"
        return tier, why
    except Exception as e:                      # noqa: BLE001
        return 2, f"classifier error, defaulting to sub-routine: {e!r}"
