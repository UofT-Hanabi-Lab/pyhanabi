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
        try:
            return HanaSimPlayer(PlayerName(player_type), player_id)
        except ValueError:
            pass

        raise ValueError("Unknown player type")


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
                result.append(g.run())
                times.append(time.time() - t0)
                # TODO: change back or add flag
                # avg_times.append(times[-1] * 1.0 / g.turn)
                print(
                    ".",
                )
            print()
            print("scores:", result)
            print("times:", times)
            print("avg times:", avg_times)

        return

    players: list[Player] = []

    for i, a in enumerate(args):
        players.append(make_player(a, i))

    n = 10000

    out: Any = NullStream()
    if n < 3:
        out = sys.stdout

    pts = []
    for i in list(range(n)):
        if (i + 1) % 100 == 0:
            print("Starting game", i + 1)
        random.seed(i + 1)
        # TODO: change back or add flag
        # g = Game(players, out)
        g = HanasimGame(players, out)
        try:
            pts.append(g.run())
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


if __name__ == "__main__":
    main(sys.argv[1:])
