#!/usr/bin/env python3
"""Terminal client for Capri.

Talks to capri-core if it is running (fast: the prompt cache stays warm),
otherwise falls back to running the turn loop in-process (slow first turn).

    python3 cli.py            interactive
    python3 cli.py "hello"    one shot
    python3 cli.py --serve    run the core server
    python3 cli.py --memory   what she durably knows

In a session:
    remember that ...   store a fact        /memory   list stored facts
    forget ...          delete a fact       /recall X what recall finds for X
"""
from __future__ import annotations
import json, sys, urllib.request, urllib.error

PORT = 8787
RED, GREEN, VIOLET, DIM, RESET = (
    "\033[38;2;255;0;51m", "\033[38;2;0;255;85m",
    "\033[38;2;138;60;232m", "\033[38;2;108;96;140m", "\033[0m",
)


def server_up() -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/health", timeout=1) as r:
            return r.status == 200
    except Exception:
        return False


def get(path: str):
    with urllib.request.urlopen(f"http://127.0.0.1:{PORT}{path}", timeout=10) as r:
        return json.loads(r.read())


def post(path: str, payload: dict):
    req = urllib.request.Request(
        f"http://127.0.0.1:{PORT}{path}", data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())


def show_memory() -> int:
    """Durable memory, read from the core if it is up, else straight off disk."""
    if server_up():
        m = get("/memory")
        facts, stats = m["facts"], m
    else:
        from capri.orchestrator import Capri
        bot = Capri()
        facts, stats = bot.facts.bullets(), bot.store.stats()
    print(f"{RED}FACTS{RESET} {DIM}({len(facts)} stored){RESET}")
    for f in facts:
        print(f"  {DIM}-{RESET} {f}")
    print(f"\n{RED}EPISODIC{RESET} {DIM}{stats['turns']} turns, "
          f"{stats['episodes']} exchanges, {stats['embedded']} embedded{RESET}")
    return 0


def ask_server(text: str) -> str:
    req = urllib.request.Request(
        f"http://127.0.0.1:{PORT}/chat",
        data=json.dumps({"text": text}).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=300) as r:
        return json.loads(r.read())["text"]


def main() -> int:
    if "--memory" in sys.argv:
        return show_memory()

    if "--serve" in sys.argv:
        from capri.server import main as serve
        print(f"{RED}capri-core{RESET} {DIM}listening on 127.0.0.1:{PORT}{RESET}")
        serve()
        return 0

    via_server = server_up()
    if via_server:
        send = ask_server
        where = f"{GREEN}core{RESET}"
    else:
        from capri.orchestrator import Capri
        bot = Capri()
        if not bot.local.available():
            print(f"{RED}ollama is not reachable at {bot.local.host}{RESET}")
            return 1
        send = bot.turn
        where = f"{DIM}in-process (start the core with --serve for fast turns){RESET}"

    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if args:
        print(send(" ".join(args)))
        return 0

    print(f"{RED}CAPRI{RESET} {DIM}·{RESET} {where} {DIM}· ctrl-d to quit{RESET}\n")
    while True:
        try:
            line = input(f"{GREEN}you{RESET} ")
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if not line.strip():
            continue
        if line.strip() in {"/quit", "/exit"}:
            return 0
        if line.strip() == "/memory":
            show_memory(); print()
            continue
        if line.strip().startswith("/recall "):
            q = line.strip()[8:]
            if via_server:
                hits = post("/recall", {"text": q, "k": 5})["hits"]
            else:
                hits = bot.store.recall(q, k=5, min_score=0.0)
            for h in hits:
                mark = GREEN if h["score"] >= 0.58 else DIM
                head = h["summary"].splitlines()[0][:70]
                print(f"  {mark}{h['score']}{RESET} {DIM}{h['ts']}{RESET} {head}")
            if not hits:
                print(f"  {DIM}nothing stored yet{RESET}")
            print()
            continue
        print(f"{VIOLET}capri{RESET} {send(line)}\n")


if __name__ == "__main__":
    raise SystemExit(main())
