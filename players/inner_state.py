import random

from players import Player
from utils import get_possible, playable, Action, discardable

class InnerStatePlayer(Player):
    def __init__(self, name, pnr):
        super().__init__(name, pnr)

    def get_action(
        self, nr, hands, knowledge, trash, played, board, valid_actions, hints
    ):
        possible = []
        for k in knowledge[nr]:
            possible.append(get_possible(k))

        discards = []
        for i, p in enumerate(possible):
            if playable(p, board):
                return Action(Action.ActionType.PLAY, cnr=i)
            if discardable(p, board):
                discards.append(i)

        if discards:
            return Action(Action.ActionType.DISCARD, cnr=random.choice(discards))

        playables = []
        for i, h in enumerate(hands):
            if i != nr:
                for j, (col, n) in enumerate(h):
                    if board[col][1] + 1 == n:
                        playables.append((i, j))

        if playables and hints > 0:
            i, j = playables[0]
            if random.random() < 0.5:
                return Action(Action.ActionType.HINT_COLOR, pnr=i, col=hands[i][j][0])
            return Action(Action.ActionType.HINT_NUMBER, pnr=i, num=hands[i][j][1])

        for i, k in enumerate(knowledge):
            if i == nr:
                continue
            cards = list(range(len(k)))
            random.shuffle(cards)
            c = cards[0]
            (col, num) = hands[i][c]
            hinttype = [Action.ActionType.HINT_COLOR, Action.ActionType.HINT_NUMBER]
            if hinttype and hints > 0:
                if random.choice(hinttype) == Action.ActionType.HINT_COLOR:
                    return Action(Action.ActionType.HINT_COLOR, pnr=i, col=col)
                else:
                    return Action(Action.ActionType.HINT_NUMBER, pnr=i, num=num)

        prefer = []
        for v in valid_actions:
            if v.action_type in {
                Action.ActionType.HINT_COLOR,
                Action.ActionType.HINT_NUMBER,
            }:
                prefer.append(v)
        prefer = []
        if prefer and hints > 0:
            return random.choice(prefer)
        return random.choice(
            [Action(Action.ActionType.DISCARD, cnr=i) for i in range(len(knowledge[0]))]
        )

    def inform(self, action, player, game):
        pass
