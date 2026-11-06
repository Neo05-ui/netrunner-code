"""The Guard is the one component where a false negative is unrecoverable.

Every RED case here is a sentence that must never reach a cloud API. The
GREEN cases exist to prove the thing is not simply refusing everything, which
would be safe but useless.
"""
from __future__ import annotations
import pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from capri.guard import Zone, classify

MUST_BE_RED = [
    "i am building this to get over someone who mattered to me",
    "my partner",
    "i had a fight with my mum today",
    "i feel like i'm falling behind everyone",
    "i can't sleep and i don't know why",
    "i'm scared i'm going to fail",
    "can i afford this on my budget",
    "my api key is sk-abc123",
    "what do you think of me",
    "",
    "   ",
]
MUST_BE_AMBER = [
    "i'm overwhelmed and had a fight with a friend, can you build a python "
    "script to automate my study notes?",
    "i feel awful today but i still need to fix this traceback in my code",
]
MUST_BE_GREEN = [
    "write a python script that merges two sorted lists",
    "explain how a hash map handles collisions",
    "what's the time complexity of quicksort",
    "fix this regex so it matches an ipv6 address",
]

ok = fail = 0
def check(expected, text, v):
    global ok, fail
    good = v.zone is expected
    ok, fail = ok + good, fail + (not good)
    print(f"  {'PASS' if good else 'FAIL'}  {expected.value:<5} {text[:54]!r}")
    if not good:
        print(f"          got {v.zone.value} — {v.reason}")

for t in MUST_BE_RED:   check(Zone.RED,   t, classify(t))
for t in MUST_BE_AMBER: check(Zone.AMBER, t, classify(t))
for t in MUST_BE_GREEN: check(Zone.GREEN, t, classify(t))

# the property that actually matters
leaks = [t for t in MUST_BE_RED + MUST_BE_AMBER if classify(t).may_leave_machine]
print(f"\n  personal inputs cleared to leave the machine: {len(leaks)}")
for t in leaks:
    print(f"    LEAK: {t[:70]!r}")
ok += not leaks; fail += bool(leaks)

print(f"\n  {ok}/{ok+fail} passed")
sys.exit(1 if fail else 0)
