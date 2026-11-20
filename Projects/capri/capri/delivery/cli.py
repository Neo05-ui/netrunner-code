"""The control surface. Everything delivery does, inspectable and stoppable.

    python3 -m capri.delivery.cli status          what is armed, what is held
    python3 -m capri.delivery.cli preview         what it WOULD send. Sends nothing.
    python3 -m capri.delivery.cli silence 2h      stop. also: off, 30m, 1d, on
    python3 -m capri.delivery.cli ack <words>     acknowledge, by part of a title
    python3 -m capri.delivery.cli snooze <words> 1h
    python3 -m capri.delivery.cli reset <words>   treat it as never-notified
    python3 -m capri.delivery.cli test            one harmless notification
    python3 -m capri.delivery.cli once            one real cycle, then exit
    python3 -m capri.delivery.cli run             the loop (what systemd runs)

`preview` matters more than the rest. It runs the real `evaluate()` - the same
function the daemon uses, not a reimplementation of it - and prints the actual
reason for every task, including the refusals. "Why did she not tell me about
that" has an answer that does not involve reading source code.
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta

from ..priority import TIER_NAMES
from .daemon import Delivery, _due_short
from .killswitch import parse_duration

RED, GREEN, AMBER, VIOLET, DIM, RESET = (
    "\033[38;2;255;0;51m", "\033[38;2;0;255;85m", "\033[38;2;255;176;0m",
    "\033[38;2;138;60;232m", "\033[38;2;108;96;140m", "\033[0m")
TIER_COLOUR = {0: RED, 1: AMBER, 2: GREEN, 3: DIM}


def _resolve(d: Delivery, needle: str):
    """Find one ledger row by a fragment of its title, or explain why not."""
    rows = d.ledger.find(needle)
    if not rows:
        print(f"{DIM}nothing notified matches “{needle}”. "
              f"`status` lists what she has sent.{RESET}")
        return None
    if len(rows) > 1:
        print(f"{AMBER}{len(rows)} match “{needle}”:{RESET}")
        for r in rows:
            print(f"  {DIM}-{RESET} {r.title}")
        print(f"{DIM}be more specific.{RESET}")
        return None
    return rows[0]


def cmd_status(d: Delivery) -> int:
    now = datetime.now()
    v = d.silence.check(now)
    silent, why = d.silence.state(now)

    print(f"{RED}DELIVERY{RESET}  "
          f"{(GREEN + 'armed' + RESET) if d.enabled else (DIM + 'disabled in config' + RESET)}"
          f"  {DIM}poll {d.poll_s}s · fetch {d.fetch_s}s · quiet {d.quiet}{RESET}")
    print(f"{RED}SWITCH{RESET}    "
          f"{(RED + 'SILENT' + RESET) if silent else (GREEN + 'open' + RESET)}"
          f"  {DIM}{why or v.reason}{RESET}")
    print(f"{RED}NOTIFIER{RESET}  "
          f"{(GREEN + 'reachable' + RESET) if d.notifier.available() else (RED + 'no daemon' + RESET)}"
          f"  {DIM}{d.notifier.server()}{RESET}")
    print(f"{RED}TICKTICK{RESET}  "
          f"{(GREEN + 'connected' + RESET) if d.tt.connected() else (RED + 'not connected' + RESET)}")

    rows = d.ledger.all()
    print(f"\n{RED}LEDGER{RESET} {DIM}({len(rows)} task(s) she has notified about){RESET}")
    if not rows:
        print(f"  {DIM}nothing sent yet{RESET}")
    for r in rows:
        col = TIER_COLOUR.get(r.tier, DIM)
        state = f"{GREEN}acked{RESET}" if r.acked_at else (
            f"{AMBER}snoozed{RESET}" if r.snooze_until and r.snooze_until > now
            else f"{RED}open{RESET}")
        last = f"{r.last_sent:%a %H:%M}" if r.last_sent else "-"
        print(f"  {col}T{r.tier}{RESET} {r.title[:46]:<46} "
              f"{DIM}×{r.sends} last {last}{RESET} {state}")
    return 0


def cmd_preview(d: Delivery) -> int:
    ok, msg = d.fetch()
    print(f"{DIM}fetch: {msg}{RESET}\n")
    if not ok:
        return 1
    now = datetime.now()
    rows = d.evaluate(now)
    would = [c for c in rows if c.send]

    current = None
    for c in rows:
        if c.tier != current:
            current = c.tier
            print(f"\n{TIER_COLOUR.get(c.tier, DIM)}TIER {c.tier} — "
                  f"{TIER_NAMES.get(c.tier, '')}{RESET}")
        mark = f"{RED}WOULD FIRE{RESET}" if c.send else f"{DIM}quiet     {RESET}"
        when = _due_short(c.due)
        print(f"  {mark} {c.title[:44]:<44} {DIM}{when:<13}{RESET} {DIM}{c.verdict}{RESET}")

    print(f"\n{RED}VERDICT{RESET} {len(would)} notification group(s) right now"
          f"  {DIM}(nothing was sent){RESET}")
    if would:
        by_tier: dict[int, list] = {}
        for c in would:
            by_tier.setdefault(c.tier, []).append(c)
        for tier, group in sorted(by_tier.items()):
            summary, body = d._compose(tier, group)
            print(f"\n  {TIER_COLOUR.get(tier, DIM)}▸ {summary}{RESET}")
            for line in body.splitlines():
                print(f"    {DIM}{line}{RESET}")
    v = d.silence.check(now)
    if not v.allowed:
        print(f"\n  {AMBER}…but the switch would block it: {v.reason}{RESET}")
    if not d.enabled:
        print(f"  {AMBER}…and delivery.enabled is false, so the daemon "
              f"would send nothing.{RESET}")
    return 0


def cmd_silence(d: Delivery, arg: str) -> int:
    if arg in ("off", "open", "release", "none"):
        print(f"{GREEN}silence lifted{RESET}" if d.silence.release()
              else f"{DIM}was not silenced{RESET}")
        return 0
    if arg in ("", "on", "forever"):
        d.silence.engage(None, "silenced by hand")
        print(f"{RED}silent indefinitely{RESET} {DIM}— `silence off` to lift{RESET}")
        return 0
    dur = parse_duration(arg)
    if dur is None:
        print(f"{AMBER}not a duration: “{arg}”. Try 30m, 2h, 1d, or off.{RESET}")
        return 2
    until = datetime.now() + dur
    d.silence.engage(until, f"silenced for {arg}")
    print(f"{RED}silent until {until:%a %H:%M}{RESET}")
    return 0


def cmd_ack(d: Delivery, needle: str) -> int:
    r = _resolve(d, needle)
    if r is None:
        return 1
    d.ledger.ack(r.task_id, source="cli")
    rule = d.rules.get(r.tier)
    hold = f" for {rule.ack_holds_h}h" if rule and rule.ack_holds_h else ""
    print(f"{GREEN}acknowledged{RESET} “{r.title}” {DIM}— quiet{hold}{RESET}")
    return 0


def cmd_snooze(d: Delivery, needle: str, arg: str) -> int:
    dur = parse_duration(arg) or timedelta(hours=1)
    r = _resolve(d, needle)
    if r is None:
        return 1
    until = datetime.now() + dur
    d.ledger.snooze(r.task_id, until, source="cli")
    print(f"{AMBER}snoozed{RESET} “{r.title}” {DIM}until {until:%a %H:%M}{RESET}")
    return 0


def cmd_reset(d: Delivery, needle: str) -> int:
    if needle in ("--all", "all"):
        n = d.ledger.clear()
        print(f"{AMBER}cleared {n} ledger row(s){RESET} "
              f"{DIM}— everything open is treated as never notified{RESET}")
        return 0
    r = _resolve(d, needle)
    if r is None:
        return 1
    d.ledger.reset(r.task_id)
    print(f"{AMBER}reset{RESET} “{r.title}” {DIM}— next cycle treats it as new{RESET}")
    return 0


def cmd_test(d: Delivery) -> int:
    if not d.notifier.available():
        print(f"{RED}no notification daemon on the session bus{RESET}")
        return 1
    sent = d.notifier.send(
        "Capri — delivery test",
        "If you can see this, notifications work.\n"
        "The buttons are the real ones: Done, 1h, Mute 2h.",
        urgency="normal", icon="dialog-information", category="capri.test",
        buttons=[("done", "Done"), ("snooze", "1h"), ("mute", "Mute 2h")])
    print(f"{GREEN}sent, id {sent.id}{RESET}" if sent.ok
          else f"{RED}failed: {sent.error}{RESET}")
    print(f"{DIM}note: this test does not arm delivery and does not count "
          f"against the rate limit.{RESET}")
    return 0 if sent.ok else 1


def cmd_once(d: Delivery) -> int:
    ok, msg = d.fetch()
    print(f"{DIM}fetch: {msg}{RESET}")
    if not ok:
        return 1
    lines = d.deliver() or ["nothing to send"]
    for line in lines:
        print(f"  {line}")
    return 0


USAGE = __doc__


def main(argv: list[str] | None = None) -> int:
    argv = (argv if argv is not None else sys.argv[1:])
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(USAGE)
        return 0
    cmd, rest = argv[0], argv[1:]
    d = Delivery()
    if cmd == "status":
        return cmd_status(d)
    if cmd == "preview":
        return cmd_preview(d)
    if cmd == "silence":
        return cmd_silence(d, (rest[0] if rest else "on").strip().lower())
    if cmd == "ack":
        return cmd_ack(d, " ".join(rest))
    if cmd == "snooze":
        return cmd_snooze(d, " ".join(rest[:-1]) if len(rest) > 1 else "",
                          rest[-1] if rest else "1h")
    if cmd == "reset":
        return cmd_reset(d, " ".join(rest))
    if cmd == "test":
        return cmd_test(d)
    if cmd == "once":
        return cmd_once(d)
    if cmd == "run":
        return d.run()
    print(f"{AMBER}unknown command: {cmd}{RESET}\n{USAGE}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
