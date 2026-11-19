#!/usr/bin/env python3
"""
Does the average score change if we play more games?

Plays each agent on decks 1..max(N) and reports the mean score over the
first N games for every requested N (default 1000, 5000, 10000). Game i
uses the same seeds as `python hanabi.py` (random.seed(i), deck seed i),
so "first 1000" here is exactly the 1000 games hanabi.py plays, and the
larger samples just add more decks on top. No log/json files are written.

Usage (from the repo root, venv active):
    python dev_tools/sample_size_check.py
    python dev_tools/sample_size_check.py --agents full full/8 --sizes 1000 5000
    python dev_tools/sample_size_check.py --jobs 5 --csv scores.csv

An agent is one player spec, the same words you pass to hanabi.py
(full, full/8, case, ...). Every seat gets that spec (self-play).
"""

import argparse
import csv
import math
import random
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from multiprocessing import get_context
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

DEFAULT_AGENTS = ["full", "full/8", "case", "full/17", "full/19"]
DEFAULT_SIZES = [1000, 5000, 10000]


def make_agent_players(spec: str, n_players: int):
    """Build players the same way hanabi.py's main() does."""
    from hanabi import make_player

    players = []
    for i in range(n_players):
        if spec.startswith("full/"):
            players.append(make_player("full", i, int(spec.split("/")[1])))
        else:
            players.append(make_player(spec, i))
    return players


def play_agent(spec: str, n_games: int, n_players: int) -> list[int]:
    """Play games 1..n_games with one agent; return the score of each game.

    Runs in its own process: the hana_sim deck seed is process-global.
    """
    sys.path.insert(0, str(REPO_ROOT))
    import hana_sim  # type: ignore
    from game import HanasimGame
    from utils import NullStream

    players = make_agent_players(spec, n_players)
    scores = []
    t0 = time.time()
    for i in range(1, n_games + 1):
        # identical seeding to hanabi.py main() with the default --seed 0
        random.seed(i)
        hana_sim.set_deck_seed(i)
        g = HanasimGame(players, NullStream(), True)
        scores.append(g.run())
        if i % 1000 == 0:
            print(f"  {spec}: {i}/{n_games} games ({time.time() - t0:.0f}s)",
                  flush=True)
    return scores


def summarize(scores: list[int]) -> tuple[float, float, float]:
    """Mean, sample std, and standard error of the mean."""
    n = len(scores)
    mean = sum(scores) / n
    std = math.sqrt(sum((s - mean) ** 2 for s in scores) / (n - 1)) if n > 1 else 0.0
    return mean, std, std / math.sqrt(n)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Mean score per agent at several sample sizes."
    )
    parser.add_argument("--agents", nargs="+", default=DEFAULT_AGENTS,
                        help=f"player specs (default: {' '.join(DEFAULT_AGENTS)})")
    parser.add_argument("--sizes", nargs="+", type=int, default=DEFAULT_SIZES,
                        help="numbers of games to average over (default: 1000 5000 10000)")
    parser.add_argument("--players", type=int, default=3)
    parser.add_argument("--jobs", type=int, default=1,
                        help="agents to run in parallel (one process each)")
    parser.add_argument("--csv", type=Path,
                        help="optionally save every game's score here (seed, agent, score)")
    args = parser.parse_args()

    sizes = sorted(set(args.sizes))
    max_n = sizes[-1]
    print(f"Playing {max_n} games x {len(args.agents)} agents "
          f"({args.players} players, jobs={args.jobs})")

    with ProcessPoolExecutor(max_workers=args.jobs,
                             mp_context=get_context("spawn")) as pool:
        futures = {a: pool.submit(play_agent, a, max_n, args.players)
                   for a in args.agents}
        all_scores = {a: f.result() for a, f in futures.items()}

    if args.csv:
        with args.csv.open("w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["seed", "agent", "score"])
            for a, scores in all_scores.items():
                for seed, s in enumerate(scores, start=1):
                    w.writerow([seed, a, s])
        print(f"Saved per-game scores to {args.csv}")

    print()
    print(f"{'agent':<10} {'games':>6} {'mean':>8} {'std':>7} {'SE':>7}"
          f"   {'95% CI':<17} {'change vs ' + str(sizes[0]):>14}")
    for a, scores in all_scores.items():
        first_mean = None
        for n in sizes:
            mean, std, se = summarize(scores[:n])
            if first_mean is None:
                first_mean = mean
            ci = f"[{mean - 1.96 * se:.3f}, {mean + 1.96 * se:.3f}]"
            change = "" if n == sizes[0] else f"{mean - first_mean:+.3f}"
            print(f"{a:<10} {n:>6} {mean:>8.3f} {std:>7.3f} {se:>7.3f}"
                  f"   {ci:<17} {change:>14}")
        print()


if __name__ == "__main__":
    main()
