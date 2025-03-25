import random
from typing import override

from players.base import Player
from utils import get_possible, playable, Action, discardable, Intent, Color, pretend


class FullyIntentionalPlayer(Player):
    def __init__(self, name, pnr):
        super().__init__(name, pnr)
        self.hints = {}
        self.gothint = None
        self.last_knowledge = []
        self.last_played = []
        self.last_board = []

    @override
    def reset(self) -> None:
        self.hints = {}
        self.gothint = None
        self.last_knowledge = []
        self.last_played = []
        self.last_board = []

    def get_action(
        self, nr, hands, knowledge, trash, played, board, valid_actions, hints
    ):
        handsize = len(knowledge[0])
        possible = []  # list[list[(color, rank)]] for each card in the hand

        self.gothint = None
        for k in knowledge[nr]:
            possible.append(get_possible(k))

        # for the current player, get the cards that are certainly playable and certainly discardable
        discards = []  # index of certainly discardable cards in the hand
        plays = []  # index of certainly playable cards in the hand
        for i, p in enumerate(possible):
            if playable(p, board):
                plays.append(i)
            if discardable(p, board):
                discards.append(i)

        # for all other players, determine the ideal goal for each of their cards
        playables = []
        useless = []
        discardables = []
        othercards = trash + board
        intentions: list[Intent | None] = [None for _ in list(range(handsize))]
        for i, h in enumerate(hands):
            if i != nr:
                for j, (col, n) in enumerate(h):
                    if board[col][1] + 1 == n:
                        playables.append((i, j))
                        intentions[j] = Intent.PLAY
                    if board[col][1] <= n:
                        useless.append((i, j))
                        if not intentions[j]:
                            intentions[j] = Intent.DISCARD
                    if n < 5 and (col, n) not in othercards:
                        discardables.append((i, j))
                        if not intentions[j]:
                            intentions[j] = Intent.CAN_DISCARD

        # determine a score for each of the hints you can possibly give,
        # and give the color or rank hint with the highest calculated score
        if hints > 0:
            valid = []
            for c in Color:
                action = (Action.ActionType.HINT_COLOR, c)
                # print("HINT", COLORNAMES[c],)
                (isvalid, score) = pretend(
                    action, knowledge[1 - nr], intentions, hands[1 - nr], board, trash
                )
                # print(isvalid, score)
                if isvalid:
                    valid.append((action, score))

            for r in range(5):
                r += 1
                action = (Action.ActionType.HINT_NUMBER, r)
                # print("HINT", r,)
                (isvalid, score) = pretend(
                    action, knowledge[1 - nr], intentions, hands[1 - nr], board, trash
                )
                # print(isvalid, score)
                if isvalid:
                    valid.append((action, score))
            if valid:
                valid.sort(key=lambda x: -x[1])
                # print(valid)
                (a, s) = valid[0]
                if a[0] == Action.ActionType.HINT_COLOR:
                    return Action(Action.ActionType.HINT_COLOR, pnr=1 - nr, col=a[1])
                else:
                    return Action(Action.ActionType.HINT_NUMBER, pnr=1 - nr, num=a[1])

        for i, k in enumerate(knowledge):
            if i == nr or True:
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

    def inform(self, action, player, game):
        if action.action_type in {Action.ActionType.PLAY, Action.ActionType.DISCARD}:
            if (action.cnr, player) in self.hints:
                self.hints[(action.cnr, player)] = []
            for i in range(10):
                if (action.cnr + i + 1, player) in self.hints:
                    self.hints[(action.cnr + i, player)] = self.hints[
                        (action.cnr + i + 1, player)
                    ]
                    self.hints[(action.cnr + i + 1, player)] = []
        elif action.pnr == self.pnr:
            self.gothint = (action, player)
            self.last_knowledge = game.knowledge[:]
            self.last_board = game.board[:]
            self.last_trash = game.trash[:]
            self.played = game.played[:]
