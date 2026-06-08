import random
import sys
import time
from typing import Any
import numpy

import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from hana_sim import PlayerName  # type: ignore

from game import HanasimGame
from players import (
    Player,
    SelfIntentionalPlayerWithMemory,
    InnerStatePlayer,
    OuterStatePlayer,
    SelfRecognitionPlayer,
    IntentionalPlayer,
    SelfIntentionalPlayer,
    SelfIntentionalPlayerDetectDeadColors,
    SamplingRecognitionPlayer,
    TimedPlayer,
    LLMAgentPlayer,
)
from players.hanasim import HanaSimPlayer
from utils import NullStream

random.seed(123)

player_types = {
    "random": Player,
    "inner": InnerStatePlayer,
    "outer": OuterStatePlayer,
    "self": SelfRecognitionPlayer,
    "intentional": IntentionalPlayer,
    "sample": SamplingRecognitionPlayer,
    "full": SelfIntentionalPlayer,
    "timed": TimedPlayer,
    "full-with-mem": SelfIntentionalPlayerWithMemory,
    "full-detect-dead": SelfIntentionalPlayerDetectDeadColors,
    "llm": LLMAgentPlayer,
}
names = ["Shangdi", "Yu Di", "Tian", "Nu Wa", "Pangu"]


def make_player(player_type: str, player_id: int) -> Player:
    if player_type in player_types:
        return player_types[player_type](names[player_id], player_id)

    elif player_type.startswith("self("):
        other = player_type[5:-1]
        return SelfRecognitionPlayer(names[player_id], player_id, player_types[other])

    elif player_type.startswith("sample("):
        other = player_type[7:-1]
        if "," in other:
            othername_raw, maxtime_raw = other.split(",")
            othername = othername_raw.strip()
            maxtime = int(maxtime_raw.strip())
            return SamplingRecognitionPlayer(
                names[player_id], player_id, player_types[othername], maxtime=maxtime
            )
        return SamplingRecognitionPlayer(
            names[player_id], player_id, player_types[other]
        )

    else:
        # try to find a matching HanaSim player name
        try:
            normalized_name = player_type.strip().lower()
            for key in PlayerName.__members__:
                if normalized_name == key.lower():
                    return HanaSimPlayer(PlayerName.__members__[key], player_id)
        except KeyError:
            pass

        raise ValueError(f"Unknown player type: {player_type}")


def report_metrics(pts, ipp_lists, players, n, prefix=""):
    """
    Statistics + Histograms for game scores and per-game mean IPP.
    TODO: Refactor main() to move all evaluation results to this helper.
    """
    # --- Scores ---
    scores = pd.Series(pts, name="score")
    print("\n=== Score distribution ===")
    print(scores.describe())

    fig, ax = plt.subplots(figsize=(6, 4))
    scores.hist(bins=range(0, 27), ax=ax, edgecolor="black")  # 26 integer bins, scores 0..25
    ax.set_xlabel("Final score")
    ax.set_ylabel("Number of games")
    ax.set_title(f"Score distribution over {n} games")
    fig.tight_layout()
    fig.savefig(f"{prefix}score_distribution.png", dpi=120)
    plt.close(fig)

    # IPP: one column per player, one row per game (NaN when the player had no plays/discards)
    ipp_df = pd.DataFrame({
        f"Player {players[p].pnr}": [
            numpy.mean(ipp_lists[g][p]) if len(ipp_lists[g][p]) > 0 else numpy.nan
            for g in range(n)
        ]
        for p in range(len(players))
    })
    print("\n=== IPP distribution (per-game mean) ===")
    print(ipp_df.describe())

    axes = ipp_df.hist(bins=20, figsize=(5 * len(players), 4),
                       edgecolor="black", layout=(1, len(players)))
    for ax in numpy.ravel(axes):
        ax.set_xlabel("Mean IPP per game")
        ax.set_ylabel("Number of games")
    plt.tight_layout()
    plt.savefig(f"{prefix}ipp_distribution.png", dpi=120)
    plt.close("all")

    print(f"\nSaved {prefix}score_distribution.png and {prefix}ipp_distribution.png")


def main(args):
    post_move_metrics = True
    if not args:
        args = ["random"] * 3
    if args[0] == "trial":
        treatments = [
            ["intentional", "intentional"],
            ["intentional", "outer"],
            ["outer", "outer"],
        ]
        # [["sample(intentional, 50)", "sample(intentional, 50)"], ["sample(intentional, 100)", "sample(intentional, 100)"]] #, ["self(intentional)", "self(intentional)"], ["self", "self"]]
        print(treatments)
        for i in range(int(args[1])):
            result = []
            times = []
            avg_times: list[float] = []
            ipp_lists: list[list[list[float]]] = []
            critical_discards: list[list[int]] = []
            known_discards: list[list[int]] = []
            known_playable_plays: list[list[int]] = []
            has_playable_cards: list[list[int]] = []
            known_unplayable_plays: list[list[int]] = []
            has_unplayable_cards: list[list[int]] = []

            print("trial", i + 1)
            for t in treatments:
                random.seed(i)
                trial_players = []
                for j, player in enumerate(t):
                    trial_players.append(make_player(player, j))
                # TODO: change back or add flag
                # g = Game(trial_players, NullStream())
                g = HanasimGame(trial_players, NullStream(), post_move_metrics)



                t0 = time.time()
                result.append(g.run())

                times.append(time.time() - t0)

                if post_move_metrics:
                    metrics = g.metric_dict
                    ipp_lists.append(metrics["ipp_list"])
                    critical_discards.append(metrics["critical_discards"])
                    known_discards.append(metrics["known_discards"])
                    known_playable_plays.append(metrics["known_playable_plays"])
                    has_playable_cards.append(metrics["has_playable"])
                    known_unplayable_plays.append(metrics["known_unplayable_plays"])
                    has_unplayable_cards.append(metrics["has_unplayable"])

                # TODO: change back or add flag
                # avg_times.append(times[-1] * 1.0 / g.turn)
                print(
                    ".",
                )
            print()
            print("scores:", result)
            print("times:", times)
            print("avg times:", avg_times)

            if post_move_metrics:
                for i, player in enumerate(treatments):
                    total_valid_ipp = 0
                    sum_ipp = 0
                    for j in range(int(args[1])):
                        if len(ipp_lists[j][i]) > 0:
                            total_valid_ipp += 1
                            sum_ipp += numpy.mean(ipp_lists[j][i])

                    avg_ipp = sum_ipp / total_valid_ipp if total_valid_ipp > 0 else None


                    avg_critical_discards = sum(
                        critical_discards[j][i] for j in range(int(args[1]))
                    ) / int(args[1])

                    avg_known_discards = sum(
                        known_discards[j][i] for j in range(int(args[1]))
                    ) / int(args[1])

                    if sum(has_playable_cards[j][i] for j in range(int(args[1]))) == 0:
                        avg_known_playable_plays = 0
                    else:
                        avg_known_playable_plays = sum(
                            known_playable_plays[j][i] for j in range(int(args[1]))
                        ) / sum(has_playable_cards[j][i] for j in range(int(args[1])))

                    if sum(has_unplayable_cards[j][i] for j in range(int(args[1]))) == 0:
                        avg_known_unplayable_plays = 0
                    else:
                        avg_known_unplayable_plays = sum(
                            known_unplayable_plays[j][i] for j in range(int(args[1]))
                        ) / sum(has_unplayable_cards[j][i] for j in range(int(args[1])))

                    if avg_ipp is None:
                        print(f"IPP for {player}: No valid data")
                    else:
                        print(f"Average valid IPP count for {player}: {total_valid_ipp} out of {int(args[1])}")
                        print(f"IPP for {player}: {avg_ipp}")

                    print(f"Average critical discards for {player}: {avg_critical_discards}")
                    print(f"Average known discards for {player}: {avg_known_discards}")
                    print(f"Average known playable plays for {player}: {avg_known_playable_plays}")
                    print(f"Average known unplayable plays for {player}: {avg_known_unplayable_plays}")

        return

    players: list[Player] = []

    for i, a in enumerate(args):
        players.append(make_player(a, i))

    n = 1000

    out: Any = NullStream()
    if n < 3:
        out = sys.stdout

    pts = []
    ipp_lists = []
    critical_discards = []
    known_discards = []
    known_playable_plays = []
    has_playable_cards = []
    known_unplayable_plays = []
    has_unplayable_cards = []

    for i in list(range(n)):
        if (i + 1) % 100 == 0:
            print("Starting game", i + 1)
        random.seed(i + 1)
        # TODO: change back or add flag
        # g = Game(players, out)
        g = HanasimGame(players, out, post_move_metrics)
        pts.append(g.run())

        if post_move_metrics:
            metrics = g.metric_dict
            ipp_lists.append(metrics["ipp_list"])
            critical_discards.append(metrics["critical_discards"])
            known_discards.append(metrics["known_discards"])
            known_playable_plays.append(metrics["known_playable_plays"])
            has_playable_cards.append(metrics["has_playable"])
            known_unplayable_plays.append(metrics["known_unplayable_plays"])
            has_unplayable_cards.append(metrics["has_unplayable"])
            
    if n < 10:
        print(pts)

    print("average:", numpy.mean(pts))
    print("stddev:", numpy.std(pts, ddof=1))
    print("range", min(pts), max(pts))
    report_metrics(pts, ipp_lists, players, n, "plots/")

    if post_move_metrics:
        for i in range(len(players)):

            total_valid_ipp = 0
            sum_ipp = 0
            for j in range(n):
                if  len(ipp_lists[j][i]) > 0:
                    total_valid_ipp += 1
                    sum_ipp += numpy.mean(ipp_lists[j][i])

            avg_ipp = sum_ipp / total_valid_ipp if total_valid_ipp > 0 else None

            avg_critical_discards = sum(
                critical_discards[j][i] for j in range(n)
            ) / n

            avg_known_discards = sum(
                known_discards[j][i] for j in range(n)
            ) / n

            if sum(has_playable_cards[j][i] for j in range(n)) == 0:
                avg_known_playable_plays = 0
            else:
                avg_known_playable_plays = sum(
                    known_playable_plays[j][i] for j in range(n)
                ) / sum(has_playable_cards[j][i] for j in range(n))
            
            if sum(has_unplayable_cards[j][i] for j in range(n)) == 0:
                avg_known_unplayable_plays = 0
            else:
                avg_known_unplayable_plays = sum(
                    known_unplayable_plays[j][i] for j in range(n)
                ) / sum(has_unplayable_cards[j][i] for j in range(n))

            if avg_ipp is None:
                print(f"IPP for Player {players[i].pnr}: No valid data")
            else:
                print(f"Average valid IPP count for Player {players[i].pnr}: {total_valid_ipp} out of {n}")
                print(f"IPP for Player {players[i].pnr}: {avg_ipp}")
            print(f"Average critical discards for {players[i].pnr}: {avg_critical_discards}")
            print(f"Average known discards for {players[i].pnr}: {avg_known_discards}")
            print(f"Average known playable plays for {players[i].pnr}: {avg_known_playable_plays}")
            print(f"Average known unplayable plays for Player {players[i].pnr}: {avg_known_unplayable_plays}")

if __name__ == "__main__":
    main(sys.argv[1:])
