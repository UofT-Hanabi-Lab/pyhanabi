import random
from typing import override

from players import Player
from utils import get_possible, playable, Action, discardable


class OuterStatePlayer(Player):
    def __init__(self, name, pnr):
        super().__init__(name, pnr)
        self.hints = {}

    @override
    def reset(self) -> None:
        self.hints = {}

    def get_action(
        self, nr, hands, knowledge, trash, played, board, valid_actions, hints
    ):
        handsize = len(knowledge[0])
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
        playables.sort(key=lambda x: -hands[x[0]][x[1]][1])
        while playables and hints > 0:
            i, j = playables[0]

            hinttype = [Action.ActionType.HINT_COLOR, Action.ActionType.HINT_NUMBER]
            if (j, i) not in self.hints:
                self.hints[(j, i)] = []

            for h in self.hints[(j, i)]:
                hinttype.remove(h)

            t = None
            if hinttype:
                t = random.choice(hinttype)

            if t == Action.ActionType.HINT_NUMBER:
                self.hints[(j, i)].append(Action.ActionType.HINT_NUMBER)
                return Action(Action.ActionType.HINT_NUMBER, pnr=i, num=hands[i][j][1])
            if t == Action.ActionType.HINT_COLOR:
                self.hints[(j, i)].append(Action.ActionType.HINT_COLOR)
                return Action(Action.ActionType.HINT_COLOR, pnr=i, col=hands[i][j][0])

            playables = playables[1:]

        for i, k in enumerate(knowledge):
            if i == nr:
                continue
            cards = list(range(len(k)))
            random.shuffle(cards)
            c = cards[0]
            (col, num) = hands[i][c]
            hinttype = [Action.ActionType.HINT_COLOR, Action.ActionType.HINT_NUMBER]
            if (c, i) not in self.hints:
                self.hints[(c, i)] = []
            for h in self.hints[(c, i)]:
                hinttype.remove(h)
            if hinttype and hints > 0:
                if random.choice(hinttype) == Action.ActionType.HINT_COLOR:
                    self.hints[(c, i)].append(Action.ActionType.HINT_COLOR)
                    return Action(Action.ActionType.HINT_COLOR, pnr=i, col=col)
                else:
                    self.hints[(c, i)].append(Action.ActionType.HINT_NUMBER)
                    return Action(Action.ActionType.HINT_NUMBER, pnr=i, num=num)

        return random.choice(
            [Action(Action.ActionType.DISCARD, cnr=i) for i in list(range(handsize))]
        )

    def inform(self, action, acting_player, game):
        if action.action_type in {Action.ActionType.PLAY, Action.ActionType.DISCARD}:
            if (action.cnr, acting_player) in self.hints:
                self.hints[(action.cnr, acting_player)] = []
            for i in range(10):
                if (action.cnr + i + 1, acting_player) in self.hints:
                    self.hints[(action.cnr + i, acting_player)] = self.hints[
                        (action.cnr + i + 1, acting_player)
                    ]
                    self.hints[(action.cnr + i + 1, acting_player)] = []
