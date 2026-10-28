"""
Reports:
- mean score, final lives distribution, total misplays
- what the recipient of a hint does on its next turn, split by whether the
  giver held 8 hint tokens (V14 ignores the intention of those hints)
- critical discards, split by whether the card was playable when discarded,
  and by rank
- hint tokens available when a playable critical card was discarded
- points lost per game to dead cards (unreachable because of the trash)
  vs. to running out of time (reachable but never played)
- V17 risky plays (V17, V19, case-based): how many succeeded, how many were
  misplays, and how many of those misplays destroyed a critical card. Read
  from the "risky_play" flag of the JSON logs, so only for runs made after
  that flag was added.

Usage (from the repo root):
    python dev_tools/run_stats.py <timestamp> [--players N] [--log-dir DIR] [--json-dir DIR]
    e.g.  python dev_tools/run_stats.py 20261013_200628 --players 3
"""

import argparse
import collections
import json
import re
from pathlib import Path

COLORS = ["green", "yellow", "white", "blue", "red"]
COUNTS = {1: 3, 2: 2, 3: 2, 4: 2, 5: 1}
MAX_HINT_TOKENS = 8

MOVE_RE = re.compile(
    r"^Move (\d+): Player (\d) (hints Player (\d)|plays|discards) ?(.*)"
)
CARD_RE = re.compile(r"(\w+) (\d)")


def parse_board(line: str) -> dict[str, int]:
    """'Board: green 0, yellow 1, ...' -> {'green': 0, 'yellow': 1, ...}"""
    return {c: int(n) for c, n in CARD_RE.findall(line.split(":", 1)[1])}


def parse_trash(line: str) -> collections.Counter:
    """'Trash: red 1, blue 5' -> Counter({('red', 1): 1, ('blue', 5): 1})"""
    return collections.Counter(
        (c, int(n)) for c, n in CARD_RE.findall(line.split(":", 1)[1])
    )


def parse_game(path: Path):
    """
    Return (moves, final_score) for one game log. Each move is a dict with the
    acting player, the move kind, and the state printed *after* the move.
    """
    lines = path.read_text().splitlines()
    moves = []
    for i, line in enumerate(lines):
        m = MOVE_RE.match(line)
        if not m:
            continue
        lives, hints = map(int, re.findall(r"\d+", lines[i + 3]))
        moves.append({
            "player": int(m.group(2)),
            "kind": m.group(3).split()[0],  # hints / plays / discards
            "target": int(m.group(4)) if m.group(4) else None,
            "rest": m.group(5),
            "board": parse_board(lines[i + 1]),
            "trash": parse_trash(lines[i + 2]),
            "lives": lives,
            "hints": hints,
        })
    s = re.search(r"Final Score: (\d+)", path.read_text())
    return moves, int(s.group(1)) if s else None


def parse_risky_flags(path: Path) -> list[bool] | None:
    """
    The "risky_play" flag of every move in a JSON game log, or None if the
    log is missing or predates the flag.
    """
    if not path.is_file():
        return None
    actions = json.loads(path.read_text())["actions"]
    flags = []
    for entry in actions:
        (turn,) = entry.values()
        if "risky_play" not in turn["action"]:
            return None
        flags.append(bool(turn["action"]["risky_play"]))
    return flags


def is_critical(col: str, rank: int, board: dict[str, int], trash: collections.Counter) -> bool:
    """Whether (col, rank) is unplayed and its last copy, given the state before the move."""
    return board[col] < rank and trash[(col, rank)] == COUNTS[rank] - 1


def reachable_score(board: dict[str, int], trash: collections.Counter) -> int:
    """Max score still achievable given the board and the trash."""
    total = 0
    for c in COLORS:
        highest = 5
        for r in range(board[c] + 1, 6):
            if trash[(c, r)] == COUNTS[r]:
                highest = r - 1
                break
        total += highest
    return total


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("timestamp", help="run suffix of the log names, e.g. 20261013_200628")
    parser.add_argument("--players", type=int, help="only games with this many players")
    parser.add_argument("--log-dir", type=Path, default=Path("log"))
    parser.add_argument("--json-dir", type=Path, default=Path("json"))
    args = parser.parse_args()

    prefix = f"{args.players}p" if args.players else "*p"
    files = sorted(args.log_dir.rglob(f"{prefix}*_{args.timestamp}.txt"))
    if not files:
        parser.error(f"No logs matching {prefix}*_{args.timestamp}.txt under {args.log_dir}")

    scores = []
    final_lives = collections.Counter()
    misplays = 0
    hint_next = {True: collections.Counter(), False: collections.Counter()}
    crit = collections.Counter()
    crit_playable_tokens = collections.Counter()
    dead_loss = []
    time_loss = []
    risky = collections.Counter()
    risky_games = 0  # games whose JSON log records risky plays

    for path in files:
        moves, score = parse_game(path)
        if not moves:
            continue
        risky_flags = parse_risky_flags(args.json_dir / f"{path.stem}.json")
        if risky_flags is not None:
            assert len(risky_flags) == len(moves), f"{path}: JSON and text logs disagree on moves"
            risky_games += 1
        if score is not None:
            scores.append(score)
        final_lives[moves[-1]["lives"]] += 1

        prev_board = {c: 0 for c in COLORS}
        prev_trash = collections.Counter()
        prev_hints = MAX_HINT_TOKENS
        for k, mv in enumerate(moves):
            if mv["kind"] == "hints":
                at8 = prev_hints == MAX_HINT_TOKENS
                nxt = next((x for x in moves[k + 1:] if x["player"] == mv["target"]), None)
                if nxt:
                    if nxt["kind"] == "plays":
                        label = "play_ok" if "success" in nxt["rest"] else "play_fail"
                    else:
                        label = nxt["kind"]
                    hint_next[at8][label] += 1

            elif mv["kind"] == "plays":
                success = "success" in mv["rest"]
                if not success:
                    misplays += 1
                if risky_flags is not None and risky_flags[k]:
                    col, rank = CARD_RE.match(mv["rest"]).groups()
                    risky["total"] += 1
                    if success:
                        risky["successful"] += 1
                    else:
                        risky["misplayed"] += 1
                        if is_critical(col, int(rank), prev_board, prev_trash):
                            risky["misplayed_critical"] += 1

            elif mv["kind"] == "discards":
                col, rank = CARD_RE.match(mv["rest"]).groups()
                rank = int(rank)
                if is_critical(col, rank, prev_board, prev_trash):
                    if prev_board[col] + 1 == rank:
                        crit["playable"] += 1
                        crit_playable_tokens[prev_hints] += 1
                    else:
                        crit["not_yet_playable"] += 1
                    crit[f"rank{rank}"] += 1

            prev_board, prev_trash, prev_hints = mv["board"], mv["trash"], mv["hints"]

        reach = reachable_score(moves[-1]["board"], moves[-1]["trash"])
        dead_loss.append(25 - reach)
        time_loss.append(reach - sum(moves[-1]["board"].values()))

    n = len(dead_loss)
    print(f"Run {args.timestamp}: {len(files)} games")
    if scores:
        print(f"Mean score: {sum(scores) / len(scores):.2f}")
    print(f"Final lives: {dict(sorted(final_lives.items()))}")
    print(f"Misplays (total): {misplays}")
    print()
    total_hints = sum(sum(c.values()) for c in hint_next.values())
    print(f"Hints followed by a recipient move: {total_hints}")
    for at8 in (True, False):
        c = hint_next[at8]
        m = sum(c.values())
        if m:
            dist = ", ".join(f"{k} {v / m:.0%}" for k, v in c.most_common())
            print(f"  giver at {'8 tokens' if at8 else '<8 tokens'} ({m}): {dist}")
    print()
    print(f"Critical discards: {dict(crit)}")
    print(f"Hint tokens available when a playable critical card was discarded: "
          f"{dict(sorted(crit_playable_tokens.items()))}")
    print()
    print(f"Avg points lost per game to critical discards:         {sum(dead_loss) / n:.2f}")
    print(f"Avg points lost per game to exhausted deck: {sum(time_loss) / n:.2f}")
    print()
    if not risky_games:
        print("Risky plays: not recorded (no JSON logs with the risky_play flag)")
    else:
        t = risky["total"]
        print(f"Risky plays in {risky_games} games: {t}")
        if t:
            print(f"  successful:                 {risky['successful']} ({risky['successful'] / t:.0%})")
            print(f"  misplays:                   {risky['misplayed']} ({risky['misplayed'] / t:.0%})")
            print(f"  misplays of critical cards: {risky['misplayed_critical']} "
                  f"({risky['misplayed_critical'] / t:.0%})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
