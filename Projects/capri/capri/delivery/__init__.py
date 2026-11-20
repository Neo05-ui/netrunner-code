"""Reminder delivery: the part that speaks without being spoken to.

Everything else in Capri answers a question. This package is the only code
that interrupts Neo on its own, which makes it the only code that can make
him want her gone. The design follows from that:

  1. THE KILL SWITCH EXISTS BEFORE THE NOTIFIER.  `touch data/SILENCE` stops
     every outgoing notification, checked immediately before each send rather
     than once at startup, so it also stops a repeat loop already in flight.

  2. NO LANGUAGE MODEL IN THIS PATH.  A notification is assembled from the
     task's own title, verbatim, by `policy.decide`. The brain can be wrong;
     a popup that invents a deadline at 2am is worse than silence. Capri
     talks about tasks in her own voice in chat - here she only reports.

  3. FAIL QUIET, not closed and not open.  The Guard resolves doubt toward
     privacy; delivery resolves it toward saying nothing. Stale task data,
     an unreadable ledger, a clock it cannot classify - every one of those
     skips the send. A missed reminder costs a task. A runaway notifier
     costs the whole project.

  4. OFF BY DEFAULT.  `delivery.enabled` is false in config. Shipping the
     code does not start it; Neo arms it.
"""
from .killswitch import Silence                    # noqa: F401
from .policy import Decision, decide, QuietHours   # noqa: F401
