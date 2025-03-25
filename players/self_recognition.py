import random
from typing import override, Final
import copy

from players.base import Player
from utils import get_possible, playable, Action, discardable, Color, COUNTS, iscard

from players.outer_state import OuterStatePlayer

a = 1

def generate_hands(knowledge, used=None):
    if used is None:
        used = {}
    if len(knowledge) == 0:
        yield []
        return

    for other in generate_hands(knowledge[1:], used):
        for col in Color:
            for i, cnt in enumerate(knowledge[0][col]):
                if cnt > 0:
                    result = [(col, i + 1)] + other
                    ok = True
                    thishand = {}
                    for c, n in result:
                        if (c, n) not in thishand:
                            thishand[(c, n)] = 0
                        thishand[(c, n)] += 1
                    for c, n in thishand:
                        if used[(c, n)] + thishand[(c, n)] > COUNTS[n - 1]:
                            ok = False
                    if ok:
                        yield result


def generate_hands_simple(knowledge):
    if len(knowledge) == 0:
        yield []
        return
    for other in generate_hands_simple(knowledge[1:]):
        for col in Color:
            for i, cnt in enumerate(knowledge[0][col]):
                if cnt > 0:
                    yield [(col, i + 1)] + other


class SelfRecognitionPlayer(Player):
    gothint: tuple[Action, int] | None
    other: Final[type[Player]]

    def __init__(self, name, pnr, other=OuterStatePlayer):
        super().__init__(name, pnr)
        self.hints = {}
        self.gothint = None
        self.last_knowledge = []
        self.last_played = []
        self.last_board = []
        self.other = other

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
        possible = []

        if self.gothint:
            possiblehands = []
            wrong = 0
            used: dict[tuple[int, int], int] = {}
            for c in Color:
                for i, cnt in enumerate(COUNTS):
                    used[(c, i + 1)] = 0
            for c_tup in trash + played:
                used[c_tup] += 1

            for h in generate_hands_simple(knowledge[nr]):
                newhands = hands[:]
                newhands[nr] = h
                other = self.other("Pinocchio", self.gothint[1])
                act = other.get_action(
                    self.gothint[1],
                    newhands,
                    self.last_knowledge,
                    self.last_trash,
                    self.last_played,
                    self.last_board,
                    valid_actions,
                    hints + 1,
                )
                lastact = self.gothint[0]
                if act == lastact:
                    possiblehands.append(h)
                else:
                    wrong += 1
            # print(len(possiblehands), "would have led to", self.gothint[0], "and not:", wrong)
            # print(f(possiblehands))
            if possiblehands:
                mostlikely = [(0, 0) for i in range(len(possiblehands[0]))]
                for i in range(len(possiblehands[0])):
                    counts = {}
                    for h in possiblehands:
                        if h[i] not in counts:
                            counts[h[i]] = 0
                        counts[h[i]] += 1
                    for c in counts:
                        if counts[c] > mostlikely[i][1]:
                            mostlikely[i] = (c, counts[c])
                # print("most likely:", mostlikely)
                m = max(mostlikely, key=lambda x: x[1])
                second = mostlikely[:]
                second.remove(m)
                m2 = max(second, key=lambda x: x[1])
                if m[1] >= m2[1] * a:
                    # print(">>>>>>> deduced!", f(m[0]), m[1],"vs", f(m2[0]), m2[1])
                    knowledge = copy.deepcopy(knowledge)
                    knowledge[nr][mostlikely.index(m)] = iscard(m[0])

        self.gothint = None
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

            if Action.ActionType.HINT_NUMBER in hinttype:
                self.hints[(j, i)].append(Action.ActionType.HINT_NUMBER)
                return Action(Action.ActionType.HINT_NUMBER, pnr=i, num=hands[i][j][1])
            if Action.ActionType.HINT_COLOR in hinttype:
                self.hints[(j, i)].append(Action.ActionType.HINT_COLOR)
                return Action(Action.ActionType.HINT_COLOR, pnr=i, col=hands[i][j][0])

            playables = playables[1:]

        for i, k in enumerate(knowledge):
            if i == nr:
                continue
            cards = list(range(len(k)))
            random.shuffle(cards)
            card = cards[0]
            (col, num) = hands[i][card]
            hinttype = [Action.ActionType.HINT_COLOR, Action.ActionType.HINT_NUMBER]
            if (card, i) not in self.hints:
                self.hints[(card, i)] = []
            for h in self.hints[(card, i)]:
                hinttype.remove(h)
            if hinttype and hints > 0:
                if random.choice(hinttype) == Action.ActionType.HINT_COLOR:
                    self.hints[(card, i)].append(Action.ActionType.HINT_COLOR)
                    return Action(Action.ActionType.HINT_COLOR, pnr=i, col=col)
                else:
                    self.hints[(card, i)].append(Action.ActionType.HINT_NUMBER)
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
