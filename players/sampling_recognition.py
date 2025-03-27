import random
import copy
from typing import override, Final

from players import Player, IntentionalPlayer
from utils import get_possible, playable, Action, discardable, Color, COUNTS, iscard


a = 1


def do_sample(knowledge):
    if not knowledge:
        return []

    possible = []

    for col in Color:
        for i, c in enumerate(knowledge[0][col]):
            for j in list(range(c)):
                possible.append((col, i + 1))
    if not possible:
        return None

    other = do_sample(knowledge[1:])
    if other is None:
        return None
    sample = random.choice(possible)
    return [sample] + other


def sample_hand(knowledge):
    result = None
    while result is None:
        result = do_sample(knowledge)
    return result


used = {}
for c in Color:
    for i, cnt in enumerate(COUNTS):
        used[(c, i + 1)] = 0


def update_knowledge(knowledge, used):
    result = copy.deepcopy(knowledge)
    for r in result:
        for c, nr in used:
            r[c][nr - 1] = max(r[c][nr - 1] - used[c, nr], 0)
    return result


class SamplingRecognitionPlayer(Player):
    other: Final[type[Player]]
    maxtime: Final[int]

    def __init__(self, name, pnr, other=IntentionalPlayer, maxtime=5000):
        super().__init__(name, pnr)
        self.hints = {}
        self.gothint = None
        self.last_knowledge = []
        self.last_played = []
        self.last_board = []
        self.other = other
        self.maxtime = maxtime

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
            used = {}

            for c in trash + played:
                if c not in used:
                    used[c] = 0
                used[c] += 1

            i = 0
            while i < self.maxtime:
                i += 1
                h = sample_hand(update_knowledge(knowledge[nr], used))
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
            # print("sampled", i)
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
