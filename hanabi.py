import random
import sys
import time
from typing import Any

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


def main(args):
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

            print("trial", i + 1)
            for t in treatments:
                random.seed(i)
                trial_players = []
                for j, player in enumerate(t):
                    trial_players.append(make_player(player, j))
                # TODO: change back or add flag
                # g = Game(trial_players, NullStream())
                g = HanasimGame(trial_players, NullStream())

                

                t0 = time.time()
                result_game, metrics = g.run()
                result.append(result_game)
                times.append(time.time() - t0)

                # Comment out below lines if you don't want additional metrics
                ipp_lists.append(metrics["ipp_list"])
                critical_discards.append(metrics["critical_discards"])
                known_discards.append(metrics["known_discards"])

                # TODO: change back or add flag
                # avg_times.append(times[-1] * 1.0 / g.turn)
                print(
                    ".",
                )
            print()
            print("scores:", result)
            print("times:", times)
            print("avg times:", avg_times)

            # Comment out below lines if you don't want additional metrics
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

                if avg_ipp is None:
                    print(f"IPP for {player}: No valid data")
                else:
                    print(f"Average valid IPP count for {player}: {total_valid_ipp} out of {int(args[1])}")
                    print(f"IPP for {player}: {avg_ipp}")

                print(f"IPP for {player}: {avg_ipp}")
                print(f"Average critical discards for {player}: {avg_critical_discards}")
                print(f"Average known discards for {player}: {avg_known_discards}")

        return

    players: list[Player] = []

    for i, a in enumerate(args):
        players.append(make_player(a, i))

    n = 100

    out: Any = NullStream()
    if n < 3:
        out = sys.stdout

    pts = []
    ipp_lists = []
    critical_discards = []
    known_discards = []
    for i in list(range(n)):
        if (i + 1) % 100 == 0:
            print("Starting game", i + 1)
        random.seed(i + 1)
        # TODO: change back or add flag
        # g = Game(players, out)
        g = HanasimGame(players, out)
        try:
            pt, metrics = g.run()
            pts.append(pt)

            # Comment out below lines if you don't want additional metrics
            ipp_lists.append(metrics["ipp_list"])
            critical_discards.append(metrics["critical_discards"])
            known_discards.append(metrics["known_discards"])
            if (i + 1) % 100 == 0:
                print("score", pts[-1])
        except Exception:
            import traceback

            traceback.print_exc()
    if n < 10:
        print(pts)
    import numpy

    print("average:", numpy.mean(pts))
    print("stddev:", numpy.std(pts, ddof=1))
    print("range", min(pts), max(pts))

    # Comment out below lines if you don't want additional metrics
    for i, player in enumerate(args):

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

        if avg_ipp is None:
            print(f"IPP for {player}: No valid data")
        else:
            print(f"Average valid IPP count for {player}: {total_valid_ipp} out of {n}")
            print(f"IPP for {player}: {avg_ipp}")
        print(f"Average critical discards for {player}: {avg_critical_discards}")
        print(f"Average known discards for {player}: {avg_known_discards}")


            


if __name__ == "__main__":
    main(sys.argv[1:])
