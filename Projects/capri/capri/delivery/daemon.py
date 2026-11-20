"""The loop that decides when to speak, and the only thing that ever does.

Separate process from capri-core, on purpose. Two reasons, both of them about
failure: a bug in notification code cannot then take down the chat server he
actually talks to, and `systemctl --user stop capri-notify` is a second kill
switch that does not depend on any code in this repository being correct.

It never loads a language model. No Ollama, no persona, no prompt. The text of
a notification is the task's own title, verbatim, assembled by `policy`. Capri
discusses tasks in her own voice when he asks her in chat; this process reports
facts and nothing else, because a popup that invents a deadline is worse than
no popup at all.

Two clocks:
  fetch_s   how often TickTick is asked (default 10 min; `all_open` is one
            request per project, so a tighter poll is rude to the API for no
            gain)
  poll_s    how often the decision runs against the cached snapshot (default
            60s, so a 15-minute repeat lands within a minute of its time)

If the snapshot goes stale - no successful fetch inside `stale_after_s` -
delivery stops. Nagging him about a task he may have ticked off twenty minutes
ago is how a reminder system starts feeling like an adversary.
"""
from __future__ import annotations

import signal
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from ..config import load as load_config
from ..log import TurnLog
from ..priority import TIER_NAMES, classify
from .acks import Ledger
from .killswitch import Silence, parse_duration
from .notify import ICONS, Notifier
from .policy import (QuietHours, decide, interruptible, rules_from_config)

MAX_LISTED = 4              # titles in one notification before "+N more"


@dataclass
class Candidate:
    tier: int
    task_id: str
    title: str
    due: str | None
    priority: int
    project: str
    why: str                # from priority.classify
    verdict: str = ""       # from policy
    send: bool = False
    urgency: str = "normal"
    replace_id: int = 0


def _due_short(due: str | None) -> str:
    """A due date in HIS timezone.

    TickTick returns UTC ("...T06:00:00.000+0000") and this machine is on
    EST. Printing the raw stamp put every deadline five hours late in the
    preview - a 01:00 deadline was printed as 06:00. A
    reminder that states the wrong time is worse than no reminder.
    """
    if not due:
        return ""
    try:
        d = datetime.fromisoformat(str(due).replace("Z", "+00:00"))
    except ValueError:
        return str(due)[:16].replace("T", " ")
    if d.tzinfo is not None:
        d = d.astimezone()                  # -> the machine's local zone
    return d.strftime("%d %b %H:%M")


class Delivery:
    def __init__(self, config_path: str | Path | None = None):
        self.cfg = load_config(config_path)
        root = Path(self.cfg["_root"])
        d = self.cfg.get("delivery", {}) or {}
        self.d = d

        self.enabled = bool(d.get("enabled", False))
        self.poll_s = int(d.get("poll_s", 60))
        self.fetch_s = int(d.get("fetch_s", 600))
        self.stale_after_s = int(d.get("stale_after_s", 2700))
        self.max_per_cycle = int(d.get("max_per_cycle", 2))

        self.log = TurnLog(root, self.cfg.get("logging", {}).get("dir", "logs"))
        self.silence = Silence(
            root / d.get("silence_file", "data/SILENCE"),
            max_per_hour=int(d.get("max_per_hour", 6)))
        self.ledger = Ledger(root / d.get("db_file", "data/delivery.db"))
        self.quiet = QuietHours(d.get("quiet_hours", "01:00-08:00"))
        self.rules = rules_from_config(d.get("tiers"))
        self.notifier = Notifier(dry_run=bool(d.get("dry_run", False)),
                                 actions=bool(d.get("actions", True)))
        self.digest_at = str(d.get("digest_at", "08:30"))
        self.digest_marker = root / d.get("digest_marker", "data/last_digest")

        tcfg = self.cfg.get("tools", {}) or {}
        from ..integrations.ticktick import TickTick
        self.tt = TickTick(root / tcfg.get("ticktick_token",
                                           "data/ticktick_token.json"))
        self._snapshot: list[Candidate] = []
        self._fetched_at: datetime | None = None
        self._stop = False

    # ---------- tasks ----------
    def fetch(self) -> tuple[bool, str]:
        """Refresh the snapshot. A failure leaves the old one in place and is
        reported; staleness is what stops delivery, not the failure itself."""
        try:
            tasks = self.tt.all_open()
        except Exception as e:                  # noqa: BLE001
            return False, f"TickTick: {e}"
        try:
            names = self.tt.project_names()
        except Exception:                       # noqa: BLE001
            names = {}
        out = []
        for t in tasks:
            project = names.get(t.project_id, "")
            tier, why = classify(t.title, priority=t.priority, due=t.due,
                                 project=project)
            out.append(Candidate(tier=tier, task_id=t.id, title=t.title,
                                 due=t.due, priority=t.priority,
                                 project=project, why=why))
        self._snapshot = out
        self._fetched_at = datetime.now()
        return True, f"{len(out)} open tasks"

    def stale(self, now: datetime | None = None) -> bool:
        if self._fetched_at is None:
            return True
        return (now or datetime.now()) - self._fetched_at > timedelta(
            seconds=self.stale_after_s)

    # ---------- decide ----------
    def evaluate(self, now: datetime | None = None) -> list[Candidate]:
        """Run every open task through the gate and the policy. Pure: it
        writes nothing and sends nothing, which is what makes `preview`
        trustworthy as a rehearsal rather than a separate code path."""
        now = now or datetime.now()
        out = []
        for c in sorted(self._snapshot, key=lambda x: (x.tier, x.due or "9999")):
            ok, gate_why = interruptible(tier=c.tier, due=c.due,
                                         priority=c.priority, now=now,
                                         rules=self.rules)
            if not ok:
                c.verdict, c.send = gate_why, False
                out.append(c)
                continue
            dec = decide(tier=c.tier, sent=self.ledger.sent_for(c.task_id),
                         now=now, rules=self.rules, quiet=self.quiet)
            c.verdict, c.send = dec.reason, dec.send
            c.urgency, c.replace_id = dec.urgency, dec.replace_id
            out.append(c)
        return out

    # ---------- send ----------
    def _compose(self, tier: int, group: list[Candidate]) -> tuple[str, str]:
        name = TIER_NAMES.get(tier, f"tier {tier}")
        head = (f"{len(group)} × {name}" if len(group) > 1 else name)
        lines = []
        for c in group[:MAX_LISTED]:
            when = _due_short(c.due)
            lines.append(f"• {c.title}" + (f"  —  due {when}" if when else ""))
        if len(group) > MAX_LISTED:
            lines.append(f"• +{len(group) - MAX_LISTED} more")
        return head, "\n".join(lines)

    def deliver(self, now: datetime | None = None) -> list[str]:
        """One cycle. Returns a line per action taken, for the log and the CLI."""
        now = now or datetime.now()
        notes: list[str] = []

        if not self.enabled:
            return ["delivery is disabled in config"]
        if self.stale(now):
            age = ("never fetched" if self._fetched_at is None
                   else f"{(now - self._fetched_at).total_seconds()/60:.0f}m old")
            return [f"snapshot {age} — staying quiet"]

        due = [c for c in self.evaluate(now) if c.send]
        if not due:
            return []

        # One notification per tier, not one per task. Three overdue deadlines
        # should be one card listing three things, not three popups that
        # repeat independently every fifteen minutes. The ledger stays
        # per-task so a single item can still be acknowledged on its own.
        by_tier: dict[int, list[Candidate]] = {}
        for c in due:
            by_tier.setdefault(c.tier, []).append(c)

        for tier in sorted(by_tier)[:self.max_per_cycle]:
            group = by_tier[tier]
            # checked immediately before EVERY send, never once per cycle: he
            # may hit Mute on the first popup while the second is being built
            v = self.silence.check(now)
            if not v.allowed:
                notes.append(f"held tier {tier} ({len(group)} tasks): {v.reason}")
                self.log.write(event="delivery_held", tier=tier,
                               tasks=len(group), reason=v.reason)
                break

            summary, body = self._compose(tier, group)
            replace = next((c.replace_id for c in group if c.replace_id), 0)
            sent = self.notifier.send(
                summary, body, urgency=group[0].urgency, replace_id=replace,
                icon=ICONS.get(tier, "dialog-information"),
                buttons=[("done", "Done"), ("snooze", "1h"), ("mute", "Mute 2h")],
                category="capri.reminder")
            if not sent.ok:
                notes.append(f"tier {tier} failed to send: {sent.error}")
                self.log.write(event="delivery_error", tier=tier,
                               error=sent.error[:200])
                continue

            self.silence.record_send(now)
            for c in group:
                self.ledger.record_send(c.task_id, title=c.title, tier=c.tier,
                                        due=c.due, notif_id=sent.id, now=now)
            notes.append(f"tier {tier}: notified about {len(group)} "
                         f"task(s) [id {sent.id}]")
            self.log.write(event="delivery_sent", tier=tier, notif_id=sent.id,
                           tasks=[c.title for c in group],
                           reason=group[0].verdict)
        return notes

    # ---------- the daily digest ----------
    def digest_due(self, now: datetime) -> bool:
        try:
            hh, _, mm = self.digest_at.partition(":")
            at = now.replace(hour=int(hh), minute=int(mm), second=0,
                             microsecond=0)
        except (TypeError, ValueError):
            return False
        if now < at or now - at > timedelta(hours=2):
            return False                        # missed the window; not overnight
        try:
            return self.digest_marker.read_text().strip() != now.strftime("%Y-%m-%d")
        except OSError:
            return True

    def send_digest(self, now: datetime | None = None) -> list[str]:
        now = now or datetime.now()
        if self.stale(now):
            return ["digest skipped: stale snapshot"]
        v = self.silence.check(now)
        if not v.allowed:
            return [f"digest held: {v.reason}"]

        buckets: dict[int, list[Candidate]] = {}
        for c in self._snapshot:
            if self.rules.get(c.tier) and self.rules[c.tier].digest:
                buckets.setdefault(c.tier, []).append(c)
        if not buckets:
            return ["digest skipped: nothing worth listing"]

        lines = []
        for tier in sorted(buckets):
            group = sorted(buckets[tier], key=lambda x: x.due or "9999")
            lines.append(f"<b>TIER {tier} — {TIER_NAMES.get(tier, '')}</b>")
            for c in group[:3]:
                when = _due_short(c.due)
                lines.append(f"  • {c.title}" + (f"  ({when})" if when else ""))
            if len(group) > 3:
                lines.append(f"  • +{len(group) - 3} more")
        total = sum(len(g) for g in buckets.values())
        sent = self.notifier.send(f"Today — {total} open", "\n".join(lines),
                                  urgency="low", icon="view-calendar-day",
                                  category="capri.digest",
                                  buttons=[("mute", "Mute 2h")])
        if not sent.ok:
            return [f"digest failed: {sent.error}"]
        self.silence.record_send(now)
        try:
            self.digest_marker.parent.mkdir(parents=True, exist_ok=True)
            self.digest_marker.write_text(now.strftime("%Y-%m-%d"))
        except OSError:
            pass
        self.log.write(event="digest_sent", tasks=total)
        return [f"digest: {total} tasks across {len(buckets)} tiers"]

    # ---------- button presses ----------
    def on_action(self, notif_id: int, key: str,
                  now: datetime | None = None) -> None:
        """A click on one of the notification's buttons. Best-effort: these
        paths exist to make acknowledging easy, not to be the only way.

        `now` is injectable only so a test can hold one clock across a
        send, a click and the next cycle; in production it is the wall
        clock, because the click really did just happen.
        """
        now = now or datetime.now()
        try:
            rows = [r for r in self.ledger.all() if r.notif_id == notif_id]
            if key == "done":
                for r in rows:
                    self.ledger.ack(r.task_id, source="notification", now=now)
                self.log.write(event="ack", source="notification",
                               notif_id=notif_id, tasks=len(rows))
            elif key == "snooze":
                until = now + timedelta(hours=1)
                for r in rows:
                    self.ledger.snooze(r.task_id, until, source="notification")
                self.log.write(event="snooze", source="notification",
                               notif_id=notif_id, until=until.isoformat())
            elif key == "mute":
                self.silence.engage(now + timedelta(hours=2),
                                    "muted from a notification")
                self.log.write(event="silence", source="notification",
                               hours=2)
        except Exception as e:                  # noqa: BLE001
            self.log.write(event="action_error", error=repr(e))

    # ---------- the loop ----------
    def run(self) -> int:
        if not self.enabled:
            print("delivery.enabled is false in config.yaml — nothing to do.")
            return 0
        signal.signal(signal.SIGTERM, self._sig)
        signal.signal(signal.SIGINT, self._sig)
        self.notifier.watch_actions(self.on_action)
        self.log.write(event="delivery_start", poll_s=self.poll_s,
                       fetch_s=self.fetch_s, quiet=str(self.quiet))

        last_fetch = 0.0
        while not self._stop:
            now = datetime.now()
            if time.monotonic() - last_fetch >= self.fetch_s:
                ok, msg = self.fetch()
                last_fetch = time.monotonic()
                # log the successes too, once per fetch_s. Without this the
                # log of a quiet night is indistinguishable from the log of
                # a daemon that never managed to reach TickTick at all.
                self.log.write(event="fetch" if ok else "fetch_failed",
                               note=msg[:200])
            try:
                if self.digest_due(now):
                    for line in self.send_digest(now):
                        self.log.write(event="digest", note=line)
                for line in self.deliver(now):
                    self.log.write(event="delivery", note=line)
            except Exception as e:              # noqa: BLE001
                # a crash here must not become a crash loop that re-sends
                self.log.write(event="cycle_error", error=repr(e))
            # a short sleep in slices so SIGTERM is answered promptly
            for _ in range(max(1, self.poll_s)):
                if self._stop:
                    break
                time.sleep(1)
        self.notifier.stop()
        self.log.write(event="delivery_stop")
        return 0

    def _sig(self, *_a) -> None:
        self._stop = True
