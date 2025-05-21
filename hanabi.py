import random
import sys
import time

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

from game import HanasimGame


class NullStream:
    def write(self, *args):
        pass


random.seed(123)

playertypes = {
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


def make_player(player, i):
    if player in playertypes:
        return playertypes[player](names[i], i)
    elif player.startswith("self("):
        other = player[5:-1]
        return SelfRecognitionPlayer(names[i], i, playertypes[other])
    elif player.startswith("sample("):
        other = player[7:-1]
        if "," in other:
            othername, maxtime = other.split(",")
            othername = othername.strip()
            maxtime = int(maxtime.strip())
            return SamplingRecognitionPlayer(
                names[i], i, playertypes[othername], maxtime=maxtime
            )
        return SamplingRecognitionPlayer(names[i], i, playertypes[other])
    return None


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
            avgtimes = []
            print("trial", i + 1)
            for t in treatments:
                random.seed(i)
                players = []
                for j, player in enumerate(t):
                    players.append(make_player(player, j))
                # TODO: change back or add flag
                # g = Game(players, NullStream())
                g = HanasimGame(players)
                t0 = time.time()
                result.append(g.run())
                times.append(time.time() - t0)
                # TODO: change back or add flag
                # avgtimes.append(times[-1] * 1.0 / g.turn)
                print(
                    ".",
                )
            print()
            print("scores:", result)
            print("times:", times)
            print("avg times:", avgtimes)

        return

    players = []

    for i, a in enumerate(args):
        players.append(make_player(a, i))

    # TODO: change back to n = 10000
    n = 10
    # TODO: change back or add flag
    # out = NullStream()
    # if n < 3:
    #     out = sys.stdout
    pts = []
    for i in list(range(n)):
        if (i + 1) % 100 == 0:
            print("Starting game", i + 1)
        random.seed(i + 1)
        # TODO: change back or add flag
        # g = Game(players, out)
        g = HanasimGame(players)
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
