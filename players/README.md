# Players (`players/`)

Every AI in this folder subclasses `Player` (`base.py`) and implements two methods:

- `get_action(nr, hands, knowledge, trash, played, board, valid_actions, hints)` — return the
  `Action` to take this turn.
- `inform(action, player, game)` — observe another player's (or your own) move so the agent can
  update its internal state.

`nr` is the acting player's index, `hands` holds every *other* player's visible cards,
`knowledge[player][card][color][rank]` is a remaining-count table for each card's possible identity,
and `board`/`trash`/`played`/`hints` describe the shared game state. The knowledge helpers used
throughout (`get_possible`, `playable`, `discardable`, `pretend`, `whattodo`, …) live in `utils.py`.

The agents below are ordered roughly from simplest to most sophisticated. The CLI key (used by
`hanabi.py <players...>`) and `httpui.py` registration name are noted where they exist. Each entry
also carries a metadata line:

- **Players** — how many players the agent's logic actually supports. The engine allows 2–5
  (`MIN_PLAYERS`/`MAX_PLAYERS` in `game.py`; hand size 5 for 2–3, 4 for 4–5). Three cases:
  - **`2 & 3`** — explicitly coded for those counts (e.g. `full`'s next-vs-subsequent `% 3` branching).
  - **`2 only`** — built around the 2-player idiom (`1 - nr`, a single "other" player); produces
    wrong/degenerate moves at higher counts.
  - **`2–5`** — player-count-agnostic: `get_action` loops over all teammates generically, so it
    yields legal moves at any count the engine allows. This means "runs without breaking," *not*
    "strategically tuned for" more than 2 — these are the simpler heuristics.
- **Last edited** — date and short hash of the most recent commit to touch that file.

---

## `Player` — random baseline (`base.py`, CLI `random`)

*Players: 2–5 · Last edited: 2026-06-23 (`f871768`)*

The base class itself is a playable agent: `get_action` just returns `random.choice(valid_actions)`
and `inform` is a no-op. It keeps no state and reasons about nothing — it exists as the interface
every other player implements and as a trivial control opponent.

## `InnerStatePlayer` (`inner_state.py`, CLI `inner`)

*Players: 2–5 · Last edited: 2025-06-21 (`4ec7bb3`)*

The simplest *rule-based* agent (Osawa's "inner state"). On its turn it plays any card it can prove
is playable from its own knowledge, otherwise discards a provably-safe card, otherwise hints a
teammate about a card they can play right now — but it picks the hint type (color vs. number) at
random and keeps **no memory of past hints**, so it may repeat the same clue. It reasons only about
its *own* deduced knowledge plus what a single hint would reveal.

## `OuterStatePlayer` (`outer_state.py`, CLI `outer`)

*Players: 2–5 · Last edited: 2025-03-26 (`7b6a6a2`)*

Osawa's "outer state": the same play/discard/hint priority as `InnerStatePlayer`, but it **tracks
which hints it has already given** for each teammate card in a `self.hints` table and won't repeat a
color/number clue that was already given for that slot. `inform` shifts this bookkeeping when cards
are played or discarded so it stays aligned as hands rotate. This makes its hinting noticeably less
wasteful than the inner-state version.

## `TimedPlayer` (`timed.py`, CLI `timed`)

*Players: 2–5 (reasons about only one partner; designed for 2) · Last edited: 2025-10-12 (`15c66dd`)*

An oddball that communicates through **turn timing rather than card content**. It encodes a priority
value by sleeping for a computed duration before acting, and decodes its partner's intended card
from how long *they* took. It is a research curiosity (a side-channel/"conventions via delay"
experiment), not a strong player, and depends on real wall-clock timing to work at all.

## `IntentionalPlayer` (`intentional.py`, CLI `intentional`)

*Players: 2 only · Last edited: 2025-10-12 (`15c66dd`)*

The first "intentional" agent and the conceptual core of the strong players. Instead of hinting
mechanically, it assigns each of a teammate's cards an `Intent` (`PLAY` / `DISCARD` / `CAN_DISCARD`)
using its view of their hand, then uses `pretend()` to simulate every possible hint and score how
well the teammate's likely reaction matches that intent — rejecting hints that reveal nothing or that
would mislead. It plays/discards from its own provable knowledge first, and when it must discard with
nothing better, it uses `pretend_discard()` expected-value scoring to drop the least valuable card.
It is written for the **2-player** case (`1 - nr`). It populates `self.explanation` for the UI.

## `FullyIntentionalPlayer` (`fully_intentional.py`)

*Players: 2 only · Last edited: 2025-10-12 (`15c66dd`)*

A variant of `IntentionalPlayer` that leans **even harder on hinting**: whenever a hint token is
available it will give the best intentional hint rather than first exhausting safe plays/discards, and
its dead-card test is slightly more aggressive (`board[col] <= n`). It records extra last-turn state in
`inform`. Registered in `__init__.py` but has **no CLI key** in `hanabi.py`; it's kept for comparison
and experimentation.

## `SelfRecognitionPlayer` (`self_recognition.py`, CLI `self`, wrapper `self(<key>)`)

*Players: 2–5 (delegate-dependent) · Last edited: 2025-03-26 (`7b6a6a2`)*

Adds **self-simulation** on top of another agent. When it receives a hint, it enumerates *all* hands
it could plausibly be holding (`generate_hands_simple`) and, for each, asks a fresh instance of a
delegate player (`other`, default `OuterStatePlayer`) what *it* would have done. The hands under which
the delegate would have produced the hint it actually received become its refined belief, letting it
deduce a card's identity by "recognizing" the hinter's reasoning. Because it enumerates hands
exhaustively it can be slow. The delegate is configurable via `self(<key>)` on the CLI.

## `SamplingRecognitionPlayer` (`sampling_recognition.py`, CLI `sample`, wrapper `sample(<key>, <n>)`)

*Players: 2–5 (delegate-dependent) · Last edited: 2025-03-26 (`7b6a6a2`)*

Same recognition idea as `SelfRecognitionPlayer`, but instead of enumerating every possible hand it
**Monte-Carlo samples** up to `maxtime` candidate hands (default 5000) consistent with its knowledge,
which trades exactness for a bounded, tunable runtime on larger belief spaces. Its default delegate is
`IntentionalPlayer`. Both the delegate and the sample budget are configurable via
`sample(<key>, <n>)`.

## `SelfIntentionalPlayer` (`self_intentional.py`, CLI `full`)

*Players: 2 & 3 · Last edited: 2026-06-24 (`e904d4a`)*

The strongest rule-based agent and the default "full" AI. It combines the intentional hinting of
`IntentionalPlayer` with **acting on hints it receives**: when hinted, it runs `whattodo()` on each of
its own cards to infer whether the hinter wanted a play or a discard, and acts on that before falling
back to provable knowledge, then intentional hinting, then expected-value discard. It supports both
**2- and 3-player** games (distinguishing the next vs. subsequent teammate) and gates discards on the
hint bank to avoid wasting tokens. See the per-branch decision order below.

## `SelfIntentionalPlayerWithMemory` (`self_intentional_with_memory.py`, CLI `full-with-mem`)

*Players: 2 only · Last edited: 2025-10-12 (`15c66dd`)*

`SelfIntentionalPlayer` plus a **memory of intentions already conveyed**. It keeps
`_intents_conveyed` per card slot and suppresses a candidate hint if it wouldn't tell the teammate
anything *new* relative to what a prior hint already communicated (`"No new intentions"`), rotating
that memory as cards leave the hand. This avoids redundant re-hinting of the same intent, spending
hint tokens more efficiently over the course of a game.

## `SelfIntentionalPlayerDetectDeadColors` (`self_intentional_detect_dead_colors.py`, CLI `full-detect-dead`)

*Players: 2 only · Last edited: 2025-10-12 (`15c66dd`)*

`SelfIntentionalPlayer` extended with **dead-color detection**. It computes, via
`highest_playable_cards(board, trash)`, the highest rank each color can *ever* reach given cards
already discarded, and threads that `dead_colors` bound through its playable/discardable/intent tests
(and `ignore_dead=True` into `pretend`/`pretend_discard`). The effect: cards in a color that can no
longer be completed are correctly treated as safe discards rather than kept indefinitely.

## `HanaSimPlayer` (`hanasim.py`)

*Players: 2 & 3 (handled natively by `hana_sim`) · Last edited: 2025-10-12 (`15c66dd`)*

A thin adapter, not a Python policy: it wraps a native policy from the compiled `hana_sim` extension
(identified by a `PlayerName`). `get_action` deliberately raises — moves are produced inside the C++
engine and the Python side only holds the name/handle. Selected by passing a `hana_sim` policy name on
the CLI (matched in `make_player`'s fallback branch).

## `LLMAgentPlayer` (`llm_agent.py`, CLI `llm`)

*Players: 2–3 (hardcoded 3 player names) · Last edited: 2025-12-03 (`873451b`)*

Delegates decisions to a **large language model**. It renders the game state, rules, and conventions
into a natural-language prompt (see `prompts.py`), asks the model for an action, and parses the reply
(with fuzzy matching) back into an `Action`. Optional `use_interpretation` / `use_verification` steps
add a hint-interpretation pass and a sanity-check pass. Despite the class defaulting to
`deepseek-chat` via `base_url=https://api.deepseek.com`, `gpt*` model names route to OpenAI; it
requires `OPENAI_API_KEY`. It is by far the slowest and non-deterministic.


