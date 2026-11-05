"""Durable facts, stored as plain Markdown so they stay human-editable.

The file is the source of truth. Capri appends to it and can delete lines from
it, but nothing here rewrites what Neo wrote by hand, and the format stays
plain bullets so it opens in Obsidian or any editor.
"""
from __future__ import annotations

import re
from pathlib import Path

STOP = {
    "the", "a", "an", "my", "his", "her", "their", "that", "this", "about",
    "is", "are", "was", "were", "and", "or", "of", "to", "in", "on", "at",
    "it", "i", "me", "you", "he", "she", "they", "we", "has", "have", "had",
}


def _tokens(s: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", s.lower()) if w not in STOP}


# A fact Neo states in the first person must not read as a fact about Capri.
# Rewriting "I" to "He" needs verb conjugation ("He hate mornings"), and
# rewriting it to "You" collides with the system prompt, which calls Capri
# "you". So keep his wording exactly and attribute it. No grammar required,
# and the provenance is honest: this is what he said, not an inference.
_FIRST_PERSON = re.compile(r"\b(I|I'?m|I'?ve|I'?ll|my|mine|me|myself)\b(?![/-])", re.I)


def attribute(fact: str, who: str = "Neo") -> str:
    """Quote first-person statements; leave impersonal ones alone."""
    if _FIRST_PERSON.search(fact):
        return f'{who}: \u201c{fact}\u201d'
    return fact


class Facts:
    def __init__(self, path: Path, who: str = "Neo"):
        self.path = Path(path)
        self.who = who
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.write_text(
                "# Facts\n\n"
                "- Add one fact per line. Capri reads this every turn.\n"
                "- She can append here herself: \"remember that ...\".\n",
                encoding="utf-8",
            )

    # ---------- raw ----------
    def read(self) -> str:
        return self.path.read_text(encoding="utf-8").strip()

    def _lines(self) -> list[str]:
        return self.path.read_text(encoding="utf-8").splitlines()

    def bullets(self) -> list[str]:
        return [l.strip()[1:].strip() for l in self._lines() if l.strip().startswith("- ")]

    # ---------- write ----------
    def add(self, fact: str) -> bool:
        """True if the fact was new and is now stored."""
        fact = fact.strip().lstrip("-").strip()
        if not fact:
            return False
        if not fact.endswith((".", "!", "?")):
            fact += "."
        fact = fact[0].upper() + fact[1:]
        fact = attribute(fact, self.who)
        if fact.lower() in self.read().lower():
            return False
        text = self.path.read_text(encoding="utf-8")
        if not text.endswith("\n"):
            text += "\n"
        self.path.write_text(text + f"- {fact}\n", encoding="utf-8")
        return True

    def remove(self, query: str) -> str | None:
        """Delete the bullet that best matches `query`. Returns it, or None.

        Matching is deliberately loose: "forget the cat" should find
        "His cat is called Mochi." Exact substring wins; otherwise the line
        sharing the most meaningful words, and only if it shares enough.
        """
        q = query.strip().lstrip("-").strip().rstrip(".")
        if not q:
            return None
        lines = self._lines()
        bullets = [(i, l.strip()[1:].strip())
                   for i, l in enumerate(lines) if l.strip().startswith("- ")]
        if not bullets:
            return None

        target = None
        for i, b in bullets:
            if q.lower() in b.lower():
                target = (i, b)
                break

        if target is None:
            qt = _tokens(q)
            if not qt:
                return None
            best, best_score = None, 0.0
            for i, b in bullets:
                bt = _tokens(b)
                if not bt:
                    continue
                score = len(qt & bt) / len(qt)
                if score > best_score:
                    best, best_score = (i, b), score
            # below this, "forget everything about X" would delete a random line
            if best is None or best_score < 0.5:
                return None
            target = best

        idx, bullet = target
        del lines[idx]
        self.path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
        return bullet
