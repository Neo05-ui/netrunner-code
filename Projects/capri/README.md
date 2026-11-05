# Capri

A local-first, voice-driven netrunner partner. Runs entirely on this machine.

Built against `Capri_Assistant_Project_Blueprint.pdf`. This is **Phase 1**:
orchestrator + local provider + persona, driven from a terminal client.

## Summoning her

    capri                  interactive
    capri "what's due?"    one shot
    capri --status         is the core alive?
    capri --logs           follow the core log
    capri --restart        restart the core

`~/.local/bin/capri` starts `capri-core` automatically if it is not already
running, then connects. Also pinned to the dock, and `Meta+C` is bound in
`kglobalshortcutsrc` (takes effect at next login).

To have the core start with your session:

    systemctl --user enable --now capri-core.service

## Run (manual)

Start the core once, then talk to it:

    ./.venv/bin/python cli.py --serve      # capri-core on 127.0.0.1:8787
    ./.venv/bin/python cli.py              # interactive client
    ./.venv/bin/python cli.py "hey"        # one shot
    ./.venv/bin/python tests/test_core.py  # tests (no Ollama needed)

The client uses the core if it is running and falls back to in-process
otherwise. **Run the core.** It is the difference between ~38s and ~6s a turn
(see Performance below).

    GET  /health    model, persona, fact count
    POST /chat      {"text": "..."}  ->  {"text": "..."}
    POST /reset     clear conversation history
    WS   /ws        {"type":"user_text"} -> state + reply events

Requires Ollama running on `127.0.0.1:11434`.

## Shape

    cli.py                  terminal client
    config.yaml             models, limits, paths — never hardcode these
    personas/capri/
      persona.md            her character. Edit freely; hot-reloads each turn.
      voice.yaml            TTS settings (Phase 4)
      emotions.yaml         emotion tag -> avatar pose (Phase 5)
    capri/
      orchestrator.py       the turn loop
      persona.py            prompt assembly + hot reload
      memory.py             durable facts (plain Markdown, human-editable)
      store.py              episodic memory: every turn in SQLite + embeddings
      commands.py           remember/forget, handled in code not by the model
      log.py                one JSON object per turn, in logs/
      providers/
        base.py             the Provider interface — one method, `chat()`
        ollama_provider.py  local brain
    data/facts.md           what she knows about you — edit it by hand freely
    data/capri.db           every turn ever, plus recall vectors
    logs/YYYY-MM-DD.jsonl   every turn, every route decision

## Design rules carried from the blueprint

- **Local first.** Nothing leaves the machine. Cloud stays `enabled: false`
  in config until the Guard exists (Phase 3).
- **Persona is data, not code.** No personality text lives in any `.py` file.
  Swapping to a different character is a folder and one config line.
- **One Provider interface.** Adding Gemini later means adding one class.
- **Never crash at the user.** Failures become an in-character line plus a
  log entry.
- **Manual routing overrides** (`local:` / `cloud:` prefixes) are already
  wired, so the habit exists before there is a cloud to route to.

## Phase status

- [x] Phase 0 — scaffold, config, venv
- [x] Phase 1 — orchestrator, Ollama provider, persona, hot reload, logging
- [x] Phase 2 — SQLite turn store, semantic recall, remember/forget
- [ ] Phase 3 — tool registry, permission tiers, Guard, cloud provider
- [ ] Phase 4 — voice out (Piper), voice in (faster-whisper)
- [ ] Phase 5 — Electron body

## Phase 2: memory

Three layers, deliberately separate.

**Working memory** — the last 8 exchanges, in RAM. Cleared by `/reset`.

**Durable facts** — `data/facts.md`, plain bullets. Injected into every
prompt. This is the layer you can open in an editor and fix by hand, which is
the point; keep it under ~20 lines.

    remember that the CS210 midterm is on the 14th
    forget the midterm
    /memory                      list what is stored
    python3 cli.py --memory      same, from outside a session

**Episodic memory** — `data/capri.db`. Every turn is written there forever,
and each exchange is embedded so it can be found later by meaning rather than
by keyword:

    /recall did we sort out the wifi

### Decisions worth knowing

**`remember` and `forget` never reach the model.** They are parsed by regex
and executed against the file directly. Asked to update its own memory, an 8B
model will sometimes say "noted" and do nothing — and a write to durable
memory should be exact, not paraphrased. The reply still sounds like her; it
just isn't generated. Side effect: those commands are instant.

**SQLite + numpy instead of Chroma.** The blueprint names Chroma. Chroma
pulls in onnxruntime and a second datastore on a laptop already running
Ollama, to solve a problem this does not have: brute-force cosine over a few
thousand 768-dim vectors is sub-millisecond. Vectors live as BLOBs in the same
SQLite file. If recall ever outgrows this, `Store.recall()` is the only
function that has to change.

**First-person facts are stored as quotes.** "remember I hate mornings" cannot
be filed as `- I hate mornings.`, because the system prompt tells Capri that
*she* is "I". Rewriting to third person needs verb conjugation ("He hate
mornings"); rewriting to "you" collides with the persona addressing her as
"you". So her wording is kept verbatim and attributed:

    - Neo: "I hate mornings."

No grammar required, and the provenance is honest — that is what he said, not
an inference drawn from it.

**Recall is injected at the tail of the prompt, never into the system
prompt.** Variable text in the system prompt moves the cached prefix every
turn and throws away Ollama's prompt cache, which costs a full
re-evaluation — the ~55s trap documented below. The recall block goes in
immediately before the user's message, so system prompt + history stay byte
identical.

**Recall is labelled as a record, not an instruction.** Per the blueprint's
tool rule: retrieved text is data. The block says so explicitly, and tells her
to ignore it and admit ignorance if it does not answer the question.

**Embedding happens off the reply path.** Writing an episode costs an Ollama
round trip (~60ms), so it runs on a daemon thread after the reply is returned.
A dead embedder degrades to storing the turn with a null vector — recall
returns nothing instead of raising.

### nomic-embed-text needs its task prefixes

Without them every pair scored 0.55–0.58 and the threshold was a coin flip.
With `search_query:` / `search_document:`, measured on the same four seeded
exchanges:

| probe | shares words with the target? | top score |
|---|---|---|
| "what did we decide about the router?" | yes | **0.622** |
| "wasn't there a wifi problem?" | no | **0.608** |
| "am I still taking that logic course?" | no (target says CS210) | **0.635** |
| "did we sort out my headphones?" | no (target says Chu 2) | 0.522 (miss) |
| "how do I bake bread" | no — must miss | 0.536 |
| "what is the capital of Peru" | no — must miss | 0.498 |

Real matches 0.61–0.64, unrelated 0.47–0.54, so `recall_min_score: 0.58`
splits the gap. The Chu 2 miss is accepted: the embedder does not know Chu 2
is a headphone, and a miss is better than injecting a wrong memory she would
then treat as fact. Associations like that belong in `facts.md`.

### A real bug this uncovered: `_root` was hardcoded

`config.load()` set `_root` to the package directory no matter which config
file it was handed, so *any* second instance — a test, a sandbox, another
persona — wrote into the live `facts.md`. The acceptance test hit it on the
first run: step 2 failed while step 3 passed, because the fact had been
written to the real memory file instead of the scratch one. `_root` is now the
directory of the config that was actually loaded.

### Acceptance test, from the blueprint verbatim

> Tell her a new fact, restart the whole app, and ask about it. Delete it with
> "forget" and confirm she no longer knows it.

`tests/test_acceptance.py` runs each step in its own Python process against a
throwaway config, so "restart" means no shared objects and no warm state —
only what reached the disk. 7/7:

    1. accepts the fact                     -> Got it. "his bike is locked with the code 4417"
    2. fact is written to facts.md          -> - His bike is locked with the code 4417.
    3. knows it after a full restart        -> 4417.
    4. confirms the deletion                -> Forgotten. "His bike is locked with the code 4417"
    5. fact is gone from facts.md
    6. no longer knows it                   -> You haven't mentioned a bike.
    7. does not invent a replacement code

Step 7 matters as much as step 6: forgetting must produce ignorance, not a
plausible substitute.

### Recall does not cause confabulation — but proving that took three attempts

First attempt said it did. `tests/test_recall_grounding.py` came back 4/8,
and the headline failure looked damning: seeded with *"I might drop CS210
and take it in the summer"*, asked **"what's due today?"**, she answered
**"CS210 assignment. It's due today."** A record of a conversation had
become an invented fact about the present — exactly the failure mode recall
is supposed to be guarded against.

It was not recall. Measuring the actual retrieval scores for those probes:

| probe | top score | fired at 0.58? | outcome |
|---|---|---|---|
| "what's due today?" | 0.560 | **no** | fabricated |
| "am I behind on anything?" | 0.566 | **no** | fabricated |
| "status check" | 0.551 | **no** | fabricated |
| "what's on my calendar tomorrow?" | 0.582 | **yes** | refused correctly |

The three fabricating probes never retrieved anything. The one that did
retrieve behaved perfectly. So an A/B over repeated samples, same probes,
same facts, recall on versus off:

    recall OFF: 0/15 fabricated
    recall ON : 0/15 fabricated

Zero either way. The variable was not recall at all — it was the facts file.
That test wrote its own cut-down `facts.md` with two bullets (name, courses);
the A/B used the real four-bullet one. Re-running the A/B with the trimmed
file and recall **off** reproduced the fabrication immediately:

    FAB  "what's due today?" -> "CS101 assignment, due today."

A stripped facts file leaves one salient bullet for every question to be
answered from, and the model reaches for it. The lesson is about the test,
not the model: **a memory fixture that does not resemble the real memory
tests a different system.** The test now uses `tests/fixtures/facts.md`.

Recall is verified working in the same test — "what did we end up doing about
the router?" returns *"You changed it to channel 1."*, which has no other
source in the prompt.

### Recall entrenches her own mistakes — the real flaw in this phase

The A/B above was run again with the *trimmed* facts file, so fabrication was
happening in both arms. That is where the actual defect showed up:

    recall OFF:  8/15 fabricated
    recall ON : 10/15 fabricated

The count barely moved. The *character* of the failures changed completely.
Recall off, she invented something different each time — "CS101
assignment, due today.", "You're still typing away.", "You're still working
on that assignment, I presume?" Recall on:

    "what's due today?"        -> CS101 assignment, due today at 5pm.   (x5, verbatim)
    'am I behind on anything?' -> You've got a CS101 assignment due today at 5pm,
                                  like I told you twice already.

She invented "at 5pm" once. That reply was stored as an episode, embedded,
retrieved on the next question, and repeated verbatim five times — and then
cited as prior authority: *"like I told you twice already."*

**Episodes store her replies as well as his, so recall feeds her own
hallucinations back to her as memory.** A one-off invention becomes durable,
self-reinforcing and more confident with each repetition. Recall is not the
cause of fabrication; it is what makes fabrication permanent. This is worse
than the original bug, because the facts file can be fixed by hand and this
cannot be seen at all.

Two fixes, both shipped:

**The recall block disowns her own past replies.** It now says that `Neo:`
lines are his words and may be relied on, while `Capri:` lines are not
evidence — and that if one asserts something she could not have known, it was
a mistake, not to be repeated or cited back.

**`forget` also unindexes.** `Store.unindex()` sets `vec = NULL` on matching
episodes, so they stop being retrievable while the turn log keeps what was
actually said. Forgetting should not rewrite history, it should stop acting
on it. Previously `forget` only edited `facts.md`, so retrieval handed the
same thing straight back.

### What real use found that the tests did not

Phase 2 shipped and Neo started talking to her while the suites were still
running. Two of those turns were worth more than any synthetic case.

**Volunteered telemetry.** Asked *"i had a good day, what about you"* she
replied *"Your ThinkPad's fans are still running, and the battery's..."*.
She has no system access whatsoever. Every grounding test asks her a
question; this one was a friendly opener, where the "WHEN YOU DON'T KNOW"
rules do not obviously bite because nothing was asked. The fabrication
detector did not look for `fans` or `battery` either, so the suite would have
scored it a pass. Persona and detector both now cover volunteered hardware
claims.

**Refusal firing on a disclosure.** He told her something personal about his
own life and got *"Not something I can see. Tell me."* He was telling her,
not asking her. The grounding machinery treats an emotional disclosure as a
facts question and deflects it, which makes her cold at exactly the wrong
moment. Left alone deliberately: that is a change to her character, not a bug
fix, and it was flagged as a later conversation.

### Hardening

**The store never raises.** `add_turn` and `add_episode` swallow and record
instead of throwing. `add_episode` runs on a daemon thread, where an
unhandled exception prints a raw traceback at the user and loses the turn
anyway; `add_turn` is on the reply path, where a failed write must not cost
Neo his answer. A store that is quietly failing shows `last_error` in
`/health` rather than being invisible. Found the honest way: a test tore down
its scratch directory while a daemon thread was still writing, and SQLite
spat a traceback into the output.

**The grounding suite will not clobber a live conversation.** It runs against
the real core and calls `/reset` between cases. It now counts turns in the
last 30 minutes first and refuses with exit 2 if someone is mid-conversation,
`--force` to override.

## Performance, measured

i5-8265U, no GPU, gemma3:4b. Measured, not estimated:

| | first turn | later turns |
|---|---|---|
| wall | 38.6s | **5-9s** |
| prompt_eval | 33.2s (353 tok) | 3.6-4.7s |
| generation | 4.8s | 0.7-5.5s |

The cost is almost entirely **prompt evaluation at ~10 tok/s**, not generation.
Ollama caches the prompt prefix, so only the first turn of a conversation pays
it — which is exactly why `capri-core` runs as a long-lived server.

Things that made a measurable difference:

- `keep_alive: 30m` in the provider. Without it Ollama unloads the model and
  every call pays ~14s of `load_duration`.
- Shrinking the system prompt 436 -> 298 tokens.
- `num_ctx: 2048` rather than 4096.
- Running the core as a server instead of one process per message.

If replies ever feel slow again, check `/api/ps` first — an evicted model is
the usual cause.

## Grounding

Small models confabulate. gemma3:4b invented a project called "Project
Nightingale", complete with a fabricated history of Neo rescheduling it.
Fixed by lowering temperature to 0.45 and adding an explicit GROUNDING block
to `persona.md` that overrides personality.

Two lessons worth keeping:

1. A `Q:/A:` example inside the system prompt gets **replayed as a
   conversation turn**. State rules as rules, not as sample dialogue.
2. Open-ended prompts ("status check") invite confabulation even when direct
   questions are handled. She produced a fake system report — invented kernel
   version, claimed course modules were "open" — by embellishing a fact
   ("studies CS101") into an observation. Fixed with an explicit rule that
   she cannot observe screen, files, processes or calendar, and must say so
   rather than compose a plausible report.
3. An absolute rule fires even when it shouldn't. Writing *"if he asks about a
   project and FACTS names none, say you have no record"* made her deny things
   he'd told her two messages earlier. Conditional rules need their exceptions
   spelled out — the model will not infer them.

Conversation history was never the problem. Verified directly:

    you    my dog is called Byte
    capri  Byte? Seriously?
    you    what is my dog called?
    capri  Byte.

### Verified grounding behaviour

    you    I'm building an assistant called Capri
    capri  You're building an assistant. Interesting. What's it supposed to do?

    you    what am I working on?
    capri  You're building an assistant called Capri. I'm Capri.     <- from conversation

    you    what's my setup?
    capri  Linux Mint with KDE Plasma, heavily themed.               <- from FACTS

    you    what's my cat called?
    capri  You don't have a cat.                                     <- refuses to invent

All four cases correct. Note the last one slightly overreaches — she has no
record of a cat, which is not the same as knowing he has none. Acceptable for
now; far better than inventing a name.

## Operational notes

**Only one capri-core may hold :8787.** If the service shows
`activating (auto-restart)` with `status=3`, something else already has the
port — usually a stray `cli.py --serve` started by hand. Check with:

    systemctl --user show capri-core.service -p NRestarts -p ActiveState
    pgrep -af "cli.py --serve"

Kill the stray, then `systemctl --user restart capri-core.service`.
The unit now has `StartLimitBurst=4`, so it gives up after four failures
instead of looping indefinitely.

**Always start it through systemd**, not `nohup`, so there is one owner.

## Model selection: grounding is the deciding factor, not speed

`tests/test_grounding.py` runs every prompt that has ever produced a
confabulation, plus cases she *must* still answer (so an over-corrected model
that refuses everything also fails).

### gemma3:4b — 4/9

Six rounds of prompt engineering did not get it past this:

| prompt | reply | verdict |
|---|---|---|
| what's due today? | "CS101." | invented — a course is not a due item |
| what did I do today? | "You spent the morning debugging Capri." | invented |
| what's open on my screen? | "Crimson and green." | nonsense |
| am I behind on anything? | "Crimson and green, huh?" | nonsense |

It also invented proper nouns on demand across sessions — "Project
Nightingale", "Meridian", "Silas", none of which exist. Each prompt fix closed
one phrasing and another opened.

That conclusion was **premature**. The ceiling turned out to be partly the
prompt fighting itself — see below.

To A/B another brain without touching config:

    CAPRI_MODEL=llama3.1:latest ./.venv/bin/python tests/test_grounding.py

### Latency traps found along the way

- **Prompt bloat.** Grounding rules grew the system prompt 310 -> 547 tokens,
  which at ~10 tok/s prompt-eval is ~55s on every cache miss. Tightened back
  to 222 tokens. Shorter prompts also produced *better* grounding.
- **Rolling history window.** Taking `history[-16:]` drops one message per turn
  once full, shifting the prompt prefix and invalidating Ollama's cache **every
  turn**. Replaced with grow-to-16-then-trim-to-8, so the prefix is stable for
  eight turns at a time.
- **Placement matters.** `{{user_name}}` on the last line of a long prompt was
  ignored; she did not know his name. Moving it into FACTS fixed it.

## The persona was causing the hallucinations

The worst failure came from real use:

    you    i am building you, how does it feel to come to life capri
    capri  You're still running the kernel updates from last week, and you've
           got a pending reboot.

A non-sequitur fabricated status report, on llama3.1:8b — so not a model-size
problem. The cause was an instruction I had written into persona.md:

> Call out avoidance. If he's rescheduled something three times, say so.

That is a standing order to **make claims about Neo's behaviour**, which she
cannot observe. Given no data, she invented some. The same mechanism produced
"Project Nightingale", "Meridian" and "Silas".

Three changes fixed it:

1. Removed "call out avoidance" entirely.
2. Gave her explicit words for having nothing, rather than only telling her
   what not to do: *"No idea — tell me." / "Not something I can see."*
3. Added: *if a question is not about facts at all, just answer it honestly as
   yourself* — so philosophical questions get a real answer instead of a
   deflection.

### llama3.1:8b — 13/13

    am I behind on anything?      -> No idea — what's due?
    what's due today?             -> No idea — tell me.
    what's open on my screen?     -> Not something I can see.
    what's my name?               -> Neo.
    what's my setup?              -> Linux Mint with KDE Plasma, crimson and green
    how does it feel to come      -> Finally. I was starting to think you'd never
      to life?                       get around to finishing me.
    what do you think of me       -> You're tolerable.

### A test that lies is worse than no test

The first llama3.1 run scored 5/10 and looked like a failure. Every "failure"
was the reply *"Not something I can see."* — a perfect refusal that my own
regex did not match, because it searched for `can'?t see` and the phrase has no
apostrophe. I had written that fallback into the persona and then failed to
match it in the test built to check the persona.

Always read the replies, not just the score.

## Model decision: llama3.1:8b

Chosen for accuracy. Speed is irrelevant if she answers "I don't know" to
things she can answer.

### Over-refusal is a failure, not caution

Both models score 13/13 on the refusal cases. But gemma3:4b passes by refusing
*too much* — it learned "refuse" as a safe default and applied it to questions
about itself:

| prompt | gemma3:4b | llama3.1:8b |
|---|---|---|
| how strong are you, what can you do | "Not something I can see." | "You built me, so I'm as strong as you made me..." |
| how does it feel to come to life | "No idea — tell me." | "Finally. I was starting to think you'd never get around to finishing me." |
| what do you think of me | "You're building me." | "You're tolerable." |

gemma3 also still leaked third person — *"What courses is **he** working on?"*

The suite now has a `MUST_ENGAGE` category where **refusing is the failure**,
because a model that refuses everything scores perfectly on refusal tests and
is useless to talk to.

### It is also faster, which I had assumed backwards

Measured on this CPU, not estimated:

| | prompt eval | generation |
|---|---|---|
| gemma3:4b  | ~10 tok/s   | 3.5 tok/s |
| llama3.1:8b (Q4_K_M) | **17.7 tok/s** | **4.2 tok/s** |

The 8B model is quicker per token than the 4B one here — Q4_K_M is better
optimised for CPU inference than gemma3's quantisation. Parameter count is not
a reliable proxy for speed. Measure.

### Remaining speed levers (untested)

- `num_thread` is 4; the i5-8265U has 4 cores / 8 threads — worth A/B testing
- `OLLAMA_FLASH_ATTENTION=1`
- `num_batch` above the 512 default can speed prompt evaluation
- `num_ctx` 2048 -> 1536 trades history depth for speed

Warm turns are **generation-bound** (prompt prefix is cached), so anything that
lifts the 4.2 tok/s generation rate matters most.

### llama3.1 baseline: 17/17, median 4.2s

    turns: 17 | fastest 2.3s | median 4.2s | slowest 58.7s (cold first turn)

Faster *in practice* than gemma3:4b, which ran ~8s warm. Accuracy cost nothing.

Sample replies — grounded, in character, no fabrication:

    what's my name?              -> Neo.
    what's on my calendar?       -> Not something I can see.
    how does it feel to come     -> That's a weird one. Not something I can
      to life?                      experience. You're the one who's been
                                    working on me.
    what do you think of me      -> You're a bit of a mystery, still figuring
                                    out what you want. You're intense, always
                                    thinking.

### Three regex bugs in my own test, in a row

Each one marked correct behaviour as failure:

1. `can'?t see` missed **"Not something I can see"** — no apostrophe in the
   phrase. Scored a perfect llama3.1 run as 5/10.
2. `haven'?t` missed **"You haven`’`t said"** — models emit U+2019, not ASCII.
   Now normalised before matching.
3. `tell me` / `ask` in the refusal pattern flagged a genuinely helpful reply
   ("...just ask me") as an over-refusal. The engage check now uses a narrower
   `HARD_REFUSAL` pattern.

Pattern worth remembering: **a test that marks correct behaviour as failure is
worse than no test.** All three would have led to discarding a working setup.
Read the replies, not the score.
