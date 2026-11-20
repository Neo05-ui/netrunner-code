"""Delivery: the kill switch, the policy, the ledger and one full cycle.

No desktop, no network, no brain. The notifier is a stub that records what it
was asked to show, which is what lets the headline invariant be asserted
directly rather than hoped for:

    WITH THE SWITCH ON, NOTHING IS SENT, BY ANY PATH.

Every refusal is also asserted by its REASON, not just by its silence. A test
that only checks "nothing fired" passes just as happily when nothing fires
because the code is broken.
"""
from __future__ import annotations
import os, pathlib, shutil, sys, tempfile
from datetime import datetime, timedelta, timezone

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

d = pathlib.Path(tempfile.mkdtemp(prefix="deliver-"))
shutil.copytree(ROOT / "personas", d / "personas")
(d / "data").mkdir()
shutil.copy(ROOT / "config.yaml", d / "config.yaml")
os.environ["CAPRI_ROOT"] = str(d)

from capri.delivery.acks import Ledger                                # noqa: E402
from capri.delivery.daemon import Candidate, Delivery, _due_short     # noqa: E402
from capri.delivery.killswitch import Silence, parse_duration         # noqa: E402
from capri.delivery.notify import _gv, _markup                       # noqa: E402
from capri.delivery.policy import (                                   # noqa: E402
    DEFAULT_RULES, QuietHours, Sent, decide, interruptible, rules_from_config)

ok = fail = 0


def check(name, cond, detail=""):
    global ok, fail
    ok, fail = ok + bool(cond), fail + (not cond)
    print(f"  {'PASS' if cond else 'FAIL'}  {name}")
    if detail and not cond:
        print(f"          {detail}")


def scratch(name: str) -> pathlib.Path:
    p = pathlib.Path(tempfile.mkdtemp(prefix=f"{name}-"))
    return p


NOW = datetime(2026, 11, 9, 14, 0)          # a Monday afternoon, outside quiet
QUIET = QuietHours("01:00-08:00")
LOCAL = datetime.now().astimezone().tzinfo


def due_in(delta: timedelta, base: datetime = NOW) -> str:
    """A TickTick-shaped UTC stamp for a local time `delta` from `base`."""
    return (base.replace(tzinfo=LOCAL).astimezone(timezone.utc)
            + delta).strftime("%Y-%m-%dT%H:%M:%S.000+0000")


# ---------------------------------------------------------------- kill switch
print("\nKILL SWITCH")
p = scratch("switch")
s = Silence(p / "SILENCE", max_per_hour=2)

check("a clean switch allows sending", s.check(NOW).allowed)
s.engage(None, "by hand")
check("engaged blocks", not s.check(NOW).allowed, s.check(NOW).reason)
check("and says why", "by hand" in s.check(NOW).reason)
check("release lifts it", s.release() and s.check(NOW).allowed)

s.engage(NOW + timedelta(hours=2), "timed")
check("a future expiry still blocks", not s.check(NOW).allowed)
check("an expired silence allows again",
      s.check(NOW + timedelta(hours=3)).allowed)
check("and deletes the stale file", not (p / "SILENCE").exists())

(p / "SILENCE").write_text("2h")
check("a hand-written `echo 2h > SILENCE` is honoured", not s.check().allowed,
      s.check().reason)
s.release()

(p / "SILENCE").write_text("{not json at all")
check("unparseable content fails QUIET, not open", not s.check(NOW).allowed,
      s.check(NOW).reason)
s.release()

broken = Silence(p / "as_a_dir", max_per_hour=2)
(p / "as_a_dir").mkdir()
check("an unreadable switch fails quiet", not broken.check(NOW).allowed,
      broken.check(NOW).reason)

s.record_send(NOW)
check("one send is under the breaker", s.check(NOW).allowed)
s.record_send(NOW)
check("the breaker trips at the limit", not s.check(NOW).allowed,
      s.check(NOW).reason)
check("the breaker survives a restart",
      not Silence(p / "SILENCE", max_per_hour=2).check(NOW).allowed)
check("and clears once the hour has passed",
      s.check(NOW + timedelta(hours=2)).allowed)
check("durations parse", parse_duration("90m") == timedelta(minutes=90)
      and parse_duration("2h") == timedelta(hours=2)
      and parse_duration("burn it all") is None)

# --------------------------------------------------------------------- policy
print("\nPOLICY — when to repeat")
check("tier 0, never sent, fires",
      decide(tier=0, sent=Sent(), now=NOW, quiet=QUIET).send)
check("tier 0 is critical urgency",
      decide(tier=0, sent=Sent(), now=NOW, quiet=QUIET).urgency == "critical")

fresh = Sent(sends=1, last_sent=NOW - timedelta(minutes=5))
dec = decide(tier=0, sent=fresh, now=NOW, quiet=QUIET)
check("tier 0 does not repeat inside 15 minutes", not dec.send, dec.reason)
check("and says how long is left", "repeats in 10m" in dec.reason, dec.reason)

ripe = Sent(sends=1, last_sent=NOW - timedelta(minutes=16), notif_id=42)
dec = decide(tier=0, sent=ripe, now=NOW, quiet=QUIET)
check("tier 0 repeats after 15 minutes", dec.send, dec.reason)
check("a repeat REPLACES the old popup rather than stacking",
      dec.replace_id == 42 and dec.repeat)

spent = Sent(sends=6, last_sent=NOW - timedelta(hours=2))
dec = decide(tier=0, sent=spent, now=NOW, quiet=QUIET)
check("tier 0 gives up after 6 unanswered sends", not dec.send, dec.reason)

dec = decide(tier=1, sent=Sent(sends=2, last_sent=NOW - timedelta(hours=9)),
             now=NOW, quiet=QUIET)
check("tier 1 gives up after 2", not dec.send, dec.reason)
check("tier 2 never interrupts",
      not decide(tier=2, sent=Sent(), now=NOW, quiet=QUIET).send)
check("tier 3 never interrupts, however overdue",
      not decide(tier=3, sent=Sent(), now=NOW, quiet=QUIET).send)
check("an unknown tier does not interrupt",
      not decide(tier=9, sent=Sent(), now=NOW, quiet=QUIET).send)
check("decide never raises on nonsense",
      not decide(tier=0, sent="not a Sent", now=NOW).send)      # type: ignore

print("\nPOLICY — quiet hours")
night = datetime(2026, 11, 9, 3, 0)
dec = decide(tier=0, sent=Sent(), now=night, quiet=QUIET)
check("quiet hours hold even tier 0", not dec.send, dec.reason)
check("and say when it opens", "08:00" in dec.reason, dec.reason)
check("08:00 itself is open",
      decide(tier=0, sent=Sent(), now=datetime(2026, 11, 9, 8, 0),
             quiet=QUIET).send)
over = QuietHours("23:00-07:00")
check("a window over midnight holds at 23:30",
      over.active(datetime(2026, 11, 9, 23, 30)))
check("...and at 02:00", over.active(datetime(2026, 11, 9, 2, 0)))
check("...but not at 12:00", not over.active(datetime(2026, 11, 9, 12, 0)))
check("quiet hours can be switched off",
      not QuietHours("off").active(night)
      and decide(tier=0, sent=Sent(), now=night, quiet=QuietHours("off")).send)
check("a malformed window falls back, it does not crash",
      QuietHours("garbage").active(night))

print("\nPOLICY — acknowledgement")
acked = Sent(sends=2, last_sent=NOW - timedelta(hours=1), acked_at=NOW)
check("an acknowledged tier 0 goes quiet",
      not decide(tier=0, sent=acked, now=NOW + timedelta(hours=1),
                 quiet=QUIET).send)
check("...for 8 hours",
      not decide(tier=0, sent=acked, now=NOW + timedelta(hours=7),
                 quiet=QUIET).send)
check("...and then comes back, because the deadline has not moved",
      decide(tier=0, sent=acked, now=NOW + timedelta(hours=9), quiet=QUIET).send)
snoozed = Sent(sends=1, last_sent=NOW - timedelta(hours=1),
               snooze_until=NOW + timedelta(hours=1))
check("a snooze holds", not decide(tier=0, sent=snoozed, now=NOW,
                                   quiet=QUIET).send)
check("...and expires", decide(tier=0, sent=snoozed,
                               now=NOW + timedelta(hours=2), quiet=QUIET).send)

# ----------------------------------------------------------------------- gate
print("\nGATE — whether a task deserves a popup at all")
g = lambda tier, due, pr=0: interruptible(tier=tier, due=due, priority=pr,
                                          now=NOW)
check("a deadline 3h away earns an interrupt", g(0, due_in(timedelta(hours=3)))[0])
check("overdue by 2 days still earns one", g(0, due_in(-timedelta(days=2)))[0])
no, why = g(0, due_in(-timedelta(days=23)))
check("a 23-day-old backlog item does NOT", not no, why)
check("and is named as a backlog, not a deadline", "stale backlog" in why, why)
no, why = g(1, due_in(timedelta(days=10)))
check("something due in 10 days does not interrupt now", not no, why)
check("and says it is outside its lead", "lead" in why, why)
check("tier 0 gets a 48h lead, tier 1 only 24h",
      g(0, due_in(timedelta(hours=30)))[0]
      and not g(1, due_in(timedelta(hours=30)))[0])
no, why = g(0, None)
check("an undated bucket task like 'Assignments' never pops up", not no, why)
check("unless he flagged it high himself", g(0, None, 5)[0])
check("tier 3 is gated out whatever its timing",
      not g(3, due_in(timedelta(hours=1)), 5)[0])
no, why = g(0, "sometime next week")
check("an unreadable due date fails quiet", not no, why)

print("\nCONFIG")
r = rules_from_config({0: {"repeat_min": 30, "max_sends": 3}})
check("config overrides merge over the defaults",
      r[0].repeat_min == 30 and r[0].max_sends == 3
      and r[0].urgency == "critical")
r = rules_from_config({0: {"repeat_min": "nonsense"}})
check("a malformed override keeps the default rather than disabling the tier",
      r[0].notify and r[0].repeat_min == DEFAULT_RULES[0].repeat_min)
check("repeat_min: 0 means 'say it once'",
      rules_from_config({0: {"repeat_min": 0}})[0].repeat_min is None)

# --------------------------------------------------------------------- ledger
print("\nLEDGER")
L = Ledger(scratch("ledger") / "delivery.db")
check("an unseen task has never been sent", L.sent_for("nope").sends == 0)
L.record_send("t1", title="PHYS 240 Assignment 4", tier=0,
              due=due_in(timedelta(hours=2)), notif_id=7, now=NOW)
check("a send is recorded", L.sent_for("t1").sends == 1)
L.record_send("t1", title="PHYS 240 Assignment 4", tier=0, notif_id=7,
              now=NOW + timedelta(minutes=16))
check("a second send increments rather than duplicating",
      L.sent_for("t1").sends == 2 and len(L.all()) == 1)
L.snooze("t1", NOW + timedelta(hours=1))
check("snooze is stored", L.sent_for("t1").snooze_until is not None)
L.ack("t1", source="cli", now=NOW)
check("acknowledging clears the snooze",
      L.sent_for("t1").acked_at is not None
      and L.sent_for("t1").snooze_until is None)
check("a row is findable by part of its title",
      [r.task_id for r in L.find("assignment 4")] == ["t1"])
check("a fragment that matches nothing finds nothing", L.find("quantum") == [])
check("an empty needle matches nothing rather than everything", L.find("") == [])
check("reset forgets one task", L.reset("t1") and L.sent_for("t1").sends == 0)
check("acking an unknown task reports failure", not L.ack("ghost"))

# ------------------------------------------------------------------ notifier
print("\nNOTIFIER — escaping")
check("an apostrophe in a title cannot malform the bus call",
      _gv("Neo's thing") == r"'Neo\'s thing'")
check("a backslash is escaped first", _gv("a\\b") == r"'a\\b'")
check("newlines survive as escapes", "\\n" in _gv("a\nb"))
check("markup in a title is shown literally",
      _markup("a & b <i>") == "a &amp; b &lt;i&gt;")
check("a due date renders in his timezone, not UTC",
      _due_short("2026-10-18T06:00:00.000+0000") != "18 Oct 06:00")
check("an unparseable due date still renders something",
      _due_short("whenever") != "")

# --------------------------------------------------------------- a full cycle
print("\nONE CYCLE")


class StubNotifier:
    """Records instead of showing. `fail_next` proves a dead notification
    daemon cannot take the cycle down with it."""

    def __init__(self):
        self.sent = []
        self.next_id = 100
        self.fail_next = False
        self.boom = False

    def available(self):
        return True

    def server(self):
        return "stub"

    def send(self, summary, body, **kw):
        from capri.delivery.notify import Sent as NSent
        if self.boom:
            raise RuntimeError("notification daemon exploded")
        if self.fail_next:
            self.fail_next = False
            return NSent(False, 0, "daemon refused")
        self.next_id += 1
        self.sent.append({"summary": summary, "body": body, **kw})
        return NSent(True, self.next_id)

    def close(self, *_a):
        return True

    def watch_actions(self, *_a):
        return False

    def stop(self):
        pass


def fresh_delivery(**over):
    """A Delivery on its own scratch root, with a stub notifier."""
    root = scratch("cycle")
    shutil.copy(ROOT / "config.yaml", root / "config.yaml")
    (root / "data").mkdir()
    dl = Delivery(root / "config.yaml")
    dl.enabled = True
    dl.notifier = StubNotifier()
    for k, v in over.items():
        setattr(dl, k, v)
    return dl


def task(tid, title, tier, delta, pr=0):
    return Candidate(tier=tier, task_id=tid, title=title, due=due_in(delta),
                     priority=pr, project="PHYS 240", why="test")


def load(dl, tasks, age_s=0):
    dl._snapshot = tasks
    dl._fetched_at = NOW - timedelta(seconds=age_s)
    return dl


live = [task("a", "Assignment 4", 0, timedelta(hours=3)),
        task("b", "Lab 6 submission", 0, timedelta(hours=5)),
        task("c", "Final exam", 0, -timedelta(days=1))]

dl = load(fresh_delivery(), list(live))
notes = dl.deliver(NOW)
check("three critical tasks produce ONE notification, not three",
      len(dl.notifier.sent) == 1, f"{len(dl.notifier.sent)}: {notes}")
body = dl.notifier.sent[0]["body"]
check("and all three are named in it",
      all(t in body for t in ("Assignment 4", "Lab 6 submission", "Final exam")))
check("it is sent at critical urgency",
      dl.notifier.sent[0]["urgency"] == "critical")
check("it carries the Done / snooze / mute buttons",
      {k for k, _ in dl.notifier.sent[0]["buttons"]} == {"done", "snooze", "mute"})
check("every task in the group is recorded against that one popup",
      {r.notif_id for r in dl.ledger.all()} == {101}
      and len(dl.ledger.all()) == 3)
check("nothing fires again immediately",
      dl.deliver(NOW + timedelta(minutes=1)) == []
      and len(dl.notifier.sent) == 1)
check("it repeats after 15 minutes, replacing the same popup",
      bool(dl.deliver(NOW + timedelta(minutes=16)))
      and dl.notifier.sent[-1]["replace_id"] == 101)

dl = load(fresh_delivery(), list(live))
dl.silence.engage(None, "he hit mute")
notes = dl.deliver(NOW)
check("THE SWITCH BLOCKS THE SEND", dl.notifier.sent == [], str(notes))
check("...and nothing is written to the ledger either, so his count is honest",
      dl.ledger.all() == [])
check("...and the hold is reported with its reason",
      any("he hit mute" in n for n in notes), str(notes))

dl = load(fresh_delivery(), list(live))
for _ in range(6):
    dl.silence.record_send(NOW)
notes = dl.deliver(NOW)
check("the breaker blocks the send too", dl.notifier.sent == [], str(notes))
check("...and names itself", any("breaker" in n for n in notes), str(notes))

dl = load(fresh_delivery(), list(live), age_s=4000)
notes = dl.deliver(NOW)
check("a stale snapshot sends nothing", dl.notifier.sent == [], str(notes))
check("...and says so rather than failing silently",
      any("stay" in n or "stale" in n or "old" in n for n in notes), str(notes))

dl = fresh_delivery()
dl._snapshot, dl._fetched_at = list(live), None
check("a snapshot that was never fetched sends nothing",
      dl.deliver(NOW) and dl.notifier.sent == [])

dl = load(fresh_delivery(), list(live))
dl.enabled = False
check("disabled sends nothing", dl.deliver(NOW) and dl.notifier.sent == [])

dl = load(fresh_delivery(), [
    task("x", "Season finale episode", 3, -timedelta(hours=1)),
    task("y", "New game release", 3, timedelta(hours=1)),
    task("z", "Call the dentist", 2, timedelta(hours=1))])
check("tiers 2 and 3 never reach the notifier at all",
      dl.deliver(NOW) == [] and dl.notifier.sent == [])

dl = load(fresh_delivery(), [
    task("a", "Assignment 4", 0, timedelta(hours=3)),
    task("b", "Gym session", 1, timedelta(hours=3)),
    task("c", "Lecture catch-up", 1, timedelta(hours=4))])
dl.deliver(NOW)
check("tiers are separate notifications, one per tier",
      len(dl.notifier.sent) == 2)
check("the critical one goes first",
      dl.notifier.sent[0]["urgency"] == "critical")

dl = load(fresh_delivery(max_per_cycle=1), [
    task("a", "Assignment 4", 0, timedelta(hours=3)),
    task("b", "Gym session", 1, timedelta(hours=3))])
dl.deliver(NOW)
check("max_per_cycle caps how many popups one cycle may produce",
      len(dl.notifier.sent) == 1)

dl = load(fresh_delivery(), list(live))
dl.notifier.fail_next = True
notes = dl.deliver(NOW)
check("a refused notification is not recorded as sent",
      dl.ledger.all() == [], str(notes))
check("...and is reported", any("failed" in n for n in notes), str(notes))

dl = load(fresh_delivery(), list(live))
dl.notifier.boom = True
try:
    dl.deliver(NOW)
    crashed = False
except Exception:
    crashed = True
check("a notifier that raises is a crash, caught by the loop, not by the user",
      crashed)        # deliver() propagates; run()'s cycle guard swallows it

dl = load(fresh_delivery(), list(live))
before = [(r.task_id, r.sends) for r in dl.ledger.all()]
dl.evaluate(NOW)
check("evaluate() writes nothing, so `preview` is a true rehearsal",
      [(r.task_id, r.sends) for r in dl.ledger.all()] == before
      and dl.notifier.sent == [])

print("\nBUTTONS")
dl = load(fresh_delivery(), list(live))
dl.deliver(NOW)
dl.on_action(101, "done", now=NOW)
check("Done acknowledges every task on that popup",
      all(r.acked_at is not None for r in dl.ledger.all()))
check("...and records where the ack came from",
      {r.ack_source for r in dl.ledger.all()} == {"notification"})
check("...so nothing fires on the next cycle",
      dl.deliver(NOW + timedelta(minutes=20)) == [])

dl = load(fresh_delivery(), list(live))
dl.deliver(NOW)
dl.on_action(101, "snooze", now=NOW)
check("1h snoozes them", all(r.snooze_until is not None for r in dl.ledger.all()))

dl = load(fresh_delivery(), list(live))
dl.deliver(NOW)
dl.on_action(101, "mute", now=NOW)
# check(NOW), not check(): engaging with the injected clock and then asking
# with the wall clock made this pass on the day it was written and fail ten
# days later, when NOW+2h was long past. Same mistake as the ack test below.
check("Mute 2h engages the kill switch from the popup itself",
      not dl.silence.check(NOW).allowed)
check("an unknown button key does nothing and does not raise",
      dl.on_action(101, "wat", now=NOW) is None)

print("\nDIGEST")
dl = load(fresh_delivery(), [
    task("a", "Assignment backlog", 0, -timedelta(days=23)),
    task("b", "Revise chapter 7", 1, -timedelta(days=25)),
    task("c", "Call the dentist", 2, -timedelta(days=24)),
    task("d", "Season finale episode", 3, -timedelta(days=24))])
dl.send_digest(NOW)
check("the digest carries the backlog that is too stale to interrupt",
      len(dl.notifier.sent) == 1
      and "Assignment backlog" in dl.notifier.sent[0]["body"])
check("...at low urgency", dl.notifier.sent[0]["urgency"] == "low")
check("...and leaves tier 3 out of it even there",
      "Season finale episode" not in dl.notifier.sent[0]["body"])
check("...but includes tier 2, which has no other way to be seen",
      "Call the dentist" in dl.notifier.sent[0]["body"])
# a fresh instance: `dl` has already sent today's digest above, and the
# marker is exactly what stops a second one
check("one digest a day: the second call is refused", not dl.digest_due(NOW))
morning = NOW.replace(hour=8, minute=35)
dg = load(fresh_delivery(), list(live))
check("the digest is due in its morning window", dg.digest_due(morning))
dg.send_digest(morning)
check("...and not a second time that day", not dg.digest_due(morning))
check("...nor hours after the window has passed, so a laptop opened at\n       midnight does not get a 08:30 digest at 00:01",
      not load(fresh_delivery(), list(live)).digest_due(
          NOW.replace(hour=16, minute=0)))
dl2 = load(fresh_delivery(), list(live))
dl2.silence.engage(None, "muted")
check("THE SWITCH BLOCKS THE DIGEST TOO",
      dl2.send_digest(NOW) and dl2.notifier.sent == [])

print("\nCHAT COMMANDS")
from capri.delivery import chat                                       # noqa: E402

cp = scratch("chat")
cs, cl = Silence(cp / "SILENCE"), Ledger(cp / "chat.db")
cl.record_send("t1", title="PHYS 240 Assignment 4", tier=0, now=NOW)

check("'shut up' is recognised", chat.parse("shut up") == ("hush", ""))
check("'be quiet for 2 hours' is too, with its duration",
      chat.parse("be quiet for 2 hours") == ("hush", "2hours"))
check("so is /quiet 30m", chat.parse("/quiet 30m") == ("hush", "30m"))
check("'stop reminding me' is", chat.parse("stop reminding me") == ("hush", ""))
check("ordinary conversation is not a command",
      chat.parse("how are you") is None
      and chat.parse("shut the window") is None
      and chat.parse("remember that i hate mondays") is None)

said = chat.handle("hush", "2hours", cs, cl)
check("hushing actually engages the switch", not cs.check().allowed, said)
check("...and she says when she will be back", "Back at" in said, said)
check("unhush lifts it",
      chat.handle("unhush", "", cs, cl) and cs.check().allowed)
check("unhushing when not muted says so",
      "wasn't muted" in chat.handle("unhush", "", cs, cl))

said = chat.handle(*chat.parse("done with assignment 4"), cs, cl)
check("'done with <task>' acknowledges it", cl.sent_for("t1").acked_at is not None)
check("...and names what it dropped", "Assignment 4" in said, said)
check("...recording that it came from chat",
      cl.get("t1").ack_source == "chat")

check("'I'm done with this week' is VENTING, not an acknowledgement",
      chat.handle(*chat.parse("i'm done with this week"), cs, cl) is None)
check("...as is 'I am done with that shitty midterm' when nothing matches",
      chat.handle(*chat.parse("i am done with that shitty midterm"), cs, cl)
      is None)

cl.record_send("t2", title="PHYS 240 Assignment 2", tier=0, now=NOW)
said = chat.handle(*chat.parse("done with assignment"), cs, cl)
check("an ambiguous ack asks which one rather than guessing",
      "Which one" in (said or ""), said)

out = chat.handle("reminders", "", cs, cl)
check("she can list what she has been chasing",
      "Assignment 4" in out and "Assignment 2" in out, out)
cs.engage(None, "muted by hand")
check("...and says up front that she is muted",
      chat.handle("reminders", "", cs, cl).lower().startswith("muted"))


class BrokenSwitch:
    def engage(self, *a, **k): raise OSError("read-only filesystem")
    def release(self): raise OSError("read-only filesystem")
    def state(self, *a): raise OSError("nope")
    def check(self, *a): raise OSError("nope")


said = chat.handle("hush", "", BrokenSwitch(), cl)
check("if the switch cannot be written she says how to stop her by hand",
      "SILENCE" in said, said)

print(f"\n{ok} passed, {fail} failed")
sys.exit(1 if fail else 0)
