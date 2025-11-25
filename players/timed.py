import time
from typing import override

from players import Player
from utils import Action

TIMESCALE = 40.0 / 1000.0  # ms
SLICETIME = TIMESCALE / 10.0
APPROXTIME = SLICETIME / 8.0

SENT: float = 0
ERRORS = 0
COUNT = 0

CAREFUL = True


def priorities(c, board):
    (col, val) = c
    if board[col][1] == val - 1:
        return val - 1
    if board[col][1] >= val:
        return 5
    if val == 5:
        return 15
    return 6 + (4 - val)


class TimedPlayer(Player):
    def __init__(self, name, pnr):
        super().__init__(name, pnr)
        self.name = name
        self.explanation = []
        self.last_tick = time.time()
        self.pnr = pnr
        self.last_played = False
        self.tt = time.time()

    @override
    def get_action(
        self, nr, hands, knowledge, trash, played, board, valid_actions, hints
    ):
        global SENT, ERRORS, COUNT
        tick = time.time()
        duration = round((tick - self.last_tick) / SLICETIME)
        other = (self.pnr + 1) % len(hands)
        # print(self.pnr, "got", duration)
        if duration >= 10:
            duration = 9
        if duration != SENT:
            ERRORS += 1
            # print("mismatch", nr, f(hands), f(board), duration, SENT)
        COUNT += 1
        other_hand = hands[other][:]

        def prio(c):
            return priorities(c, board)

        other_hand.sort(key=prio)
        # print(f(other_hand), f(board), list(list(map(prio, other_hand)), f(hands)))
        p = prio(other_hand[0])
        delta = 0.0
        if p >= 5:
            delta += 5

        # print("idx", hands[other].index(other_hand[0]))
        def fix(n):
            if n >= len(other_hand):
                return len(other_hand) - 1
            return int(round(n))

        delta += hands[other].index(other_hand[0])
        if duration >= 5:
            action = Action(Action.ActionType.DISCARD, cnr=fix(duration - 5))
        else:
            action = Action(Action.ActionType.PLAY, cnr=fix(duration))
        if self.last_played and hints > 0 and CAREFUL:
            action = Action(
                Action.ActionType.HINT_COLOR, pnr=other, col=other_hand[0][0]
            )
        t1 = time.time()
        SENT = delta
        # print(self.pnr, "convey", round(delta))
        delta -= 0.5
        while (t1 - tick) < delta * SLICETIME:
            time.sleep(APPROXTIME)
            t1 = time.time()
        self.last_tick = time.time()
        return action

    @override
    def inform(self, action, acting_player, game):
        self.last_played = action.action_type == Action.ActionType.PLAY
        self.last_tick = self.tt
        self.tt = time.time()
        # print(action, player)

    @override
    def get_explanation(self):
        return self.explanation
