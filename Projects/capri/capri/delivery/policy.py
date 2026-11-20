"""Whether to interrupt him, right now, about one task. No I/O, no model.

The entire decision lives in `decide()` as a pure function of (tier rule,
what we have already sent, the clock). That is on purpose: this is the piece
that will be wrong, and a pure function can be hammered by tests in
milliseconds without a desktop, a network or a brain.

The tiers are Neo's own interrupt matrix (see capri/priority.py):

  TIER 0  CRITICAL OVERLOAD  exams, deadlines, submissions  -> critical popup,
                                                       repeats until answered
  TIER 1  ACTIVE DIRECTIVE   workouts, milestones, meetings -> one popup, one
                                                       nudge two hours later
  TIER 2  SUB-ROUTINE        chores, calls, errands         -> digest only
  TIER 3  DOPAMINE DROP      anime, game drops              -> never. Ever.

Tier 3 having no delivery path at all is the point of having tiers. If an
anime episode can generate a popup then the matrix is decoration.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta

# One definition of "stale", shared with the classifier. If these two ever
# disagree, a task can be escalated by one module and ignored by the other.
from ..priority import STALE_AFTER, _parse_due


@dataclass(frozen=True)
class TierRule:
    notify: bool = False
    digest: bool = False
    repeat_min: int | None = None     # None = say it once, never again
    max_sends: int = 1                # then stop, even unacknowledged
    ack_holds_h: int = 24             # how long a "done" keeps it quiet
    lead_h: int = 24                  # how early a due date may interrupt
    urgency: str = "normal"           # notify-send urgency


# Tier 0 stops after six unanswered sends rather than repeating forever. An
# alarm that cannot be silenced is not urgent, it is broken, and the next
# thing he does is kill the daemon and never start it again. Six sends over
# ninety minutes is a fair attempt; after that `status` says it gave up and
# why, which is information rather than noise.
DEFAULT_RULES: dict[int, TierRule] = {
    0: TierRule(notify=True, digest=True, repeat_min=15, max_sends=6,
                ack_holds_h=8,  lead_h=48, urgency="critical"),
    1: TierRule(notify=True, digest=True, repeat_min=120, max_sends=2,
                ack_holds_h=24, lead_h=24, urgency="normal"),
    2: TierRule(notify=False, digest=True, urgency="low"),
    3: TierRule(notify=False, digest=False, urgency="low"),
}


def rules_from_config(cfg: dict | None) -> dict[int, TierRule]:
    """Merge config over the defaults. A malformed entry keeps the default
    rather than disabling the tier or, worse, inventing a louder one."""
    out = dict(DEFAULT_RULES)
    for key, over in (cfg or {}).items():
        try:
            tier = int(key)
            base = out.get(tier, TierRule())
            if not isinstance(over, dict):
                continue
            rep = over.get("repeat_min", base.repeat_min)
            out[tier] = TierRule(
                notify=bool(over.get("notify", base.notify)),
                digest=bool(over.get("digest", base.digest)),
                repeat_min=None if rep in (None, 0, False) else int(rep),
                max_sends=max(1, int(over.get("max_sends", base.max_sends))),
                ack_holds_h=max(0, int(over.get("ack_holds_h", base.ack_holds_h))),
                lead_h=max(0, int(over.get("lead_h", base.lead_h))),
                urgency=str(over.get("urgency", base.urgency)),
            )
        except (TypeError, ValueError):
            continue
    return out


_HHMM = re.compile(r"^\s*(\d{1,2}):(\d{2})\s*$")


def _hhmm(s: str, default: time) -> time:
    m = _HHMM.match(s or "")
    if not m:
        return default
    h, mi = int(m.group(1)), int(m.group(2))
    if not (0 <= h <= 23 and 0 <= mi <= 59):
        return default
    return time(h, mi)


class QuietHours:
    """A window in which nothing is delivered, including tier 0.

    Holding tier 0 overnight is a choice worth stating: a deadline popup at
    03:00 cannot be acted on, and the repeat cycle would simply burn its six
    attempts against a sleeping man and then give up before he woke. Held
    items fire when the window opens.
    """

    def __init__(self, spec: str | None = "01:00-08:00"):
        self.spec = (spec or "").strip()
        self.off = self.spec.lower() in ("", "off", "none", "false")
        start, _, end = self.spec.partition("-")
        self.start = _hhmm(start, time(1, 0))
        self.end = _hhmm(end, time(8, 0))

    def active(self, now: datetime) -> bool:
        if self.off:
            return False
        t = now.time()
        if self.start <= self.end:                  # 01:00-08:00
            return self.start <= t < self.end
        return t >= self.start or t < self.end      # 23:00-07:00, over midnight

    def next_open(self, now: datetime) -> datetime:
        if self.off or not self.active(now):
            return now
        candidate = now.replace(hour=self.end.hour, minute=self.end.minute,
                                second=0, microsecond=0)
        if candidate <= now:
            candidate += timedelta(days=1)
        return candidate

    def __str__(self) -> str:
        return "off" if self.off else f"{self.start:%H:%M}-{self.end:%H:%M}"


@dataclass
class Sent:
    """What has already happened to one task. The ledger's row, decoupled."""
    sends: int = 0
    last_sent: datetime | None = None
    acked_at: datetime | None = None
    snooze_until: datetime | None = None
    notif_id: int = 0


@dataclass
class Decision:
    send: bool
    reason: str
    urgency: str = "normal"
    replace_id: int = 0
    repeat: bool = False
    tags: list[str] = field(default_factory=list)


def decide(*, tier: int, sent: Sent, now: datetime,
           rules: dict[int, TierRule] | None = None,
           quiet: QuietHours | None = None) -> Decision:
    """Send this, right now, or not - and say why either way.

    Every branch returns a reason, including the refusals. `preview` and
    `status` print them verbatim, so "why did she not tell me" and "why did
    she tell me twice" are both answerable without reading this file.
    """
    try:
        rules = rules or DEFAULT_RULES
        rule = rules.get(int(tier))
        if rule is None:
            return Decision(False, f"tier {tier} has no rule")
        if not rule.notify:
            return Decision(False, f"tier {tier} is not a notifying tier",
                            urgency=rule.urgency)

        if quiet is not None and quiet.active(now):
            return Decision(False, f"quiet hours ({quiet}), held until "
                                   f"{quiet.next_open(now):%H:%M}",
                            urgency=rule.urgency)

        if sent.snooze_until and now < sent.snooze_until:
            return Decision(False, f"snoozed until {sent.snooze_until:%a %H:%M}",
                            urgency=rule.urgency)

        if sent.acked_at and rule.ack_holds_h:
            held_until = sent.acked_at + timedelta(hours=rule.ack_holds_h)
            if now < held_until:
                return Decision(False, f"acknowledged {sent.acked_at:%a %H:%M}, "
                                       f"quiet until {held_until:%a %H:%M}",
                                urgency=rule.urgency)

        if sent.sends <= 0 or sent.last_sent is None:
            return Decision(True, "first notification", urgency=rule.urgency)

        if rule.repeat_min is None:
            return Decision(False, "already sent once; this tier does not repeat",
                            urgency=rule.urgency)

        if sent.sends >= rule.max_sends:
            return Decision(False, f"gave up after {sent.sends} unacknowledged "
                                   f"sends (limit {rule.max_sends})",
                            urgency=rule.urgency)

        waited = now - sent.last_sent
        due_in = timedelta(minutes=rule.repeat_min) - waited
        if due_in > timedelta(0):
            mins = due_in.total_seconds() / 60
            return Decision(False, f"last sent {waited.total_seconds()/60:.0f}m "
                                   f"ago; repeats in {mins:.0f}m",
                            urgency=rule.urgency)

        return Decision(True, f"repeat {sent.sends + 1}/{rule.max_sends}, "
                              f"{waited.total_seconds()/60:.0f}m since the last",
                        urgency=rule.urgency, replace_id=sent.notif_id,
                        repeat=True)
    except Exception as e:                          # noqa: BLE001
        # An exception here must not become a popup. Delivery fails quiet.
        return Decision(False, f"policy error, staying quiet: {e!r}")


def interruptible(*, tier: int, due: str | None, priority: int = 0,
                  now: datetime | None = None,
                  rules: dict[int, TierRule] | None = None,
                  stale_after: timedelta = STALE_AFTER) -> tuple[bool, str]:
    """May this task generate a POPUP at all, before any timing question.

    A popup needs a REASON TO BE NOW. Three ways a task fails that, every one
    of them found in Neo's actual list the first time this was rehearsed
    against it:

    NO ANCHOR. A standing bucket item - a one-word task naming a whole
    category of work, no due date, sat there for months. It classifies as
    TIER 0 on its title and is right to; there is simply no moment at which
    it becomes true and no action that makes it stop. Unless he flagged it
    high himself, it is a list item, not an interrupt.

    TOO EARLY. Something due in ten days is still TIER 1, and without this
    check it would pop up the instant the daemon started. A due date earns an
    interrupt inside `lead_h` of itself, not before.

    TOO LATE. His whole list is three to four weeks overdue - it is a backlog,
    not a set of live deadlines. A critical alarm repeating every fifteen
    minutes about a submission from October is not urgent, it is abuse, and
    the first thing he would do is kill the daemon and never start it again.
    Past `stale_after` (14 days, the same threshold priority.py already uses
    so that the two modules cannot disagree) it is digest material.

    What survives all three is a task with a real, near, live deadline - which
    is exactly the set of things worth stopping him for.
    """
    rules = rules or DEFAULT_RULES
    rule = rules.get(int(tier))
    if rule is None or not rule.notify:
        return False, f"tier {tier} does not interrupt"

    if not due:
        if int(priority or 0) >= 3:
            return True, f"no due date, but he flagged it (priority {priority})"
        return False, "no due date and no priority flag - digest only"

    d = _parse_due(due)
    if d is None:
        return False, f"unreadable due date ({due!r}) - digest only"

    now = now or datetime.now()
    # compare in one frame: TickTick hands back tz-aware stamps, `now` is naive
    if d.tzinfo is not None:
        d = d.astimezone().replace(tzinfo=None)

    left = d - now
    if left > timedelta(hours=rule.lead_h):
        return False, (f"due in {left.days}d {left.seconds // 3600}h, outside "
                       f"its {rule.lead_h}h lead - digest only")
    if -left > stale_after:
        return False, (f"{(-left).days}d overdue - stale backlog, not a "
                       f"deadline; digest only")
    if left < timedelta(0):
        return True, f"overdue by {(-left).days}d {((-left).seconds // 3600)}h"
    # total_seconds, not .seconds: a 25h lead is 1 day + 1 hour, and
    # .seconds alone reported it as "due in 1h"
    return True, f"due in {left.total_seconds() / 3600:.0f}h"
