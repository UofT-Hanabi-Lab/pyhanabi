import random
import sys
import copy
import time
from enum import Enum, unique, IntEnum
from typing import Final, Sequence, override

COUNTS = [3, 2, 2, 2, 1]


@unique
class Color(IntEnum):
    GREEN = 0
    YELLOW = 1
    WHITE = 2
    BLUE = 3
    RED = 4

    @property
    def display_name(self) -> str:
        return self.name.lower()

    def __str__(self) -> str:
        return str(self.value)


@unique
class Intent(Enum):
    PLAY = 2
    DISCARD = 3
    CAN_DISCARD = 128


# semi-intelligently format cards in any format
def f(something):
    if isinstance(something, list):
        return list(map(f, something))
    elif isinstance(something, dict):
        return {k: something[v] for (k, v) in something.items()}
    elif isinstance(something, tuple) and len(something) == 2:
        assert isinstance(something[0], Color)
        return something[0].display_name, something[1]
    return something


def make_deck():
    deck = []
    for col in Color:
        for num, cnt in enumerate(COUNTS):
            for i in list(range(cnt)):
                deck.append((col, num + 1))
    random.shuffle(deck)
    return deck


def initial_knowledge():
    knowledge = []
    for _ in Color:
        knowledge.append(COUNTS[:])
    return knowledge


def hint_color(knowledge, color, truth):
    result = []
    for col in Color:
        if truth == (col == color):
            result.append(knowledge[col][:])
        else:
            result.append([0 for _ in knowledge[col]])
    return result


def hint_rank(knowledge, rank, truth):
    result = []
    for col in Color:
        colknow = []
        for i, k in enumerate(knowledge[col]):
            if truth == (i + 1 == rank):
                colknow.append(k)
            else:
                colknow.append(0)
        result.append(colknow)
    return result


def iscard(x):
    (c, n) = x
    knowledge = []
    for col in Color:
        knowledge.append(COUNTS[:])
        for i in range(len(knowledge[-1])):
            if col != c or i + 1 != n:
                knowledge[-1][i] = 0
            else:
                knowledge[-1][i] = 1

    return knowledge


class Action:
    @unique
    class ActionType(Enum):
        HINT_COLOR = 0
        HINT_NUMBER = 1
        PLAY = 2
        DISCARD = 3

        @property
        def display_name(self) -> str:
            return self.name.replace("_", " ").title()

        def __str__(self) -> str:
            return str(self.value)

    action_type: ActionType

    def __init__(
        self,
        action_type: ActionType,
        pnr: int | None = None,
        col: Color | None = None,
        num: int | None = None,
        cnr: int | None = None,
    ) -> None:
        self.action_type = action_type
        self.pnr = pnr
        self.col = col
        self.num = num
        self.cnr = cnr

    def __str__(self):
        if self.action_type == Action.ActionType.HINT_COLOR:
            assert self.col is not None
            return (
                "hints "
                + str(self.pnr)
                + " about all their "
                + self.col.display_name
                + " cards"
            )
        if self.action_type == Action.ActionType.HINT_NUMBER:
            return "hints " + str(self.pnr) + " about all their " + str(self.num)
        if self.action_type == Action.ActionType.PLAY:
            return "plays their " + str(self.cnr)
        if self.action_type == Action.ActionType.DISCARD:
            return "discards their " + str(self.cnr)

    def __eq__(self, other):
        return (self.action_type, self.pnr, self.col, self.num, self.cnr) == (
            other.action_type,
            other.pnr,
            other.col,
            other.num,
            other.cnr,
        )


class Player:
    def __init__(self, name, pnr, hand_size=5):
        self.name = name
        self.pnr = pnr
        self._hand_size: Final[int] = hand_size

        self.explanation = []

    def reset(self) -> None:
        """
        Sets the player's state back to the initial state, as though it has never played
        a game.
        """
        pass

    def get_action(
        self, nr, hands, knowledge, trash, played, board, valid_actions, hints
    ):
        return random.choice(valid_actions)

    def inform(self, action, player, game):
        pass

    def get_explanation(self):
        return self.explanation


def get_possible(knowledge):
    result = []
    for col in Color:
        for i, cnt in enumerate(knowledge[col]):
            if cnt > 0:
                result.append((col, i + 1))
    return result


def playable(possible, board):
    for col, nr in possible:
        if board[col][1] + 1 != nr:
            return False
    return True


def potentially_playable(possible, board):
    for col, nr in possible:
        if board[col][1] + 1 == nr:
            return True
    return False


def discardable(possible, board):
    for col, nr in possible:
        if board[col][1] < nr:
            return False
    return True


def potentially_discardable(possible, board):
    for col, nr in possible:
        if board[col][1] >= nr:
            return True
    return False


def update_knowledge(knowledge, used):
    result = copy.deepcopy(knowledge)
    for r in result:
        for c, nr in used:
            r[c][nr - 1] = max(r[c][nr - 1] - used[c, nr], 0)
    return result


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


a = 1


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


TIMESCALE = 40.0 / 1000.0  # ms
SLICETIME = TIMESCALE / 10.0
APPROXTIME = SLICETIME / 8.0


def priorities(c, board):
    (col, val) = c
    if board[col][1] == val - 1:
        return val - 1
    if board[col][1] >= val:
        return 5
    if val == 5:
        return 15
    return 6 + (4 - val)


SENT: float = 0
ERRORS = 0
COUNT = 0

CAREFUL = True


class TimedPlayer:
    def __init__(self, name, pnr):
        self.name = name
        self.explanation = []
        self.last_tick = time.time()
        self.pnr = pnr
        self.last_played = False
        self.tt = time.time()

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

    def inform(self, action, player, game):
        self.last_played = action.action_type == Action.ActionType.PLAY
        self.last_tick = self.tt
        self.tt = time.time()
        # print(action, player)

    def get_explanation(self):
        return self.explanation


def format_intention(i: str | Intent | None) -> str:
    if isinstance(i, str):
        return i
    if i == Intent.PLAY:
        return "Play"
    elif i == Intent.DISCARD:
        return "Discard"
    elif i == Intent.CAN_DISCARD:
        return "Can Discard"
    elif i is None:
        return "Keep"
    else:
        raise ValueError("Unexpected intent value")


def whattodo(knowledge, pointed, board) -> Action.ActionType | None:
    possible = get_possible(knowledge)
    play = potentially_playable(possible, board)
    discard = potentially_discardable(possible, board)

    if play and pointed:
        return Action.ActionType.PLAY
    if discard and pointed:
        return Action.ActionType.DISCARD
    return None


def pretend(action, knowledge, intentions, hand, board):
    (action_type, value) = action
    positive = []
    haspositive = False
    change = False
    if action_type == Action.ActionType.HINT_COLOR:
        newknowledge = []
        for i, (col, num) in enumerate(hand):
            positive.append(value == col)
            newknowledge.append(hint_color(knowledge[i], value, value == col))
            if value == col:
                haspositive = True
                if newknowledge[-1] != knowledge[i]:
                    change = True
    else:
        newknowledge = []
        for i, (col, num) in enumerate(hand):
            positive.append(value == num)

            newknowledge.append(hint_rank(knowledge[i], value, value == num))
            if value == num:
                haspositive = True
                if newknowledge[-1] != knowledge[i]:
                    change = True
    if not haspositive:
        return False, 0, ["Invalid hint"]
    if not change:
        return False, 0, ["No new information"]
    score = 0
    predictions: list[Intent | None] = []
    pos = False
    for i, c, k, p in zip(intentions, hand, newknowledge, positive):
        predicted_action = whattodo(k, p, board)

        if predicted_action == Action.ActionType.PLAY and i != Intent.PLAY:
            # print("would cause them to play", f(c))
            return False, 0, predictions + [Intent.PLAY]

        if predicted_action == Action.ActionType.DISCARD and i not in {
            Intent.DISCARD,
            Intent.CAN_DISCARD,
        }:
            # print("would cause them to discard", f(c))
            return False, 0, predictions + [Intent.DISCARD]

        if predicted_action == Action.ActionType.PLAY and i == Intent.PLAY:
            pos = True
            predictions.append(Intent.PLAY)
            score += 3
        elif predicted_action == Action.ActionType.DISCARD and i in {
            Intent.DISCARD,
            Intent.CAN_DISCARD,
        }:
            pos = True
            predictions.append(Intent.DISCARD)
            if i == Intent.DISCARD:
                score += 2
            else:
                score += 1
        else:
            predictions.append(None)
    if not pos:
        return False, score, predictions
    return True, score, predictions


HINT_VALUE = 0.5


def pretend_discard(act, knowledge, board, trash):
    which = copy.deepcopy(knowledge[act.cnr])
    for col, num in trash:
        if which[col][num - 1]:
            which[col][num - 1] -= 1
    for col in Color:
        for i in range(board[col][1]):
            if which[col][i]:
                which[col][i] -= 1
    possibilities = sum(list(map(sum, which)))
    expected = 0
    terms = []
    for col in Color:
        for i, cnt in enumerate(which[col]):
            rank = i + 1
            if cnt > 0:
                prob = cnt * 1.0 / possibilities
                if board[col][1] >= rank:
                    expected += prob * HINT_VALUE
                    terms.append((col, rank, cnt, prob, prob * HINT_VALUE))
                else:
                    dist = rank - board[col][1]
                    if cnt > 1:
                        value = prob * (6 - rank) / (dist * dist)
                    else:
                        value = 6 - rank
                    if rank == 5:
                        value += HINT_VALUE
                    value *= prob
                    expected -= value
                    terms.append((col, rank, cnt, prob, -value))
    return (act, expected, terms)


def format_knowledge(k):
    result = ""
    for col in Color:
        for i, cnt in enumerate(k[col]):
            if cnt > 0:
                result += col.display_name + " " + str(i + 1) + ": " + str(cnt) + "\n"
    return result


class IntentionalPlayer(Player):
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
        possible = []
        result = None
        self.explanation = []
        self.explanation.append(["Your Hand:"] + list(map(f, hands[1 - nr])))

        self.gothint = None
        for k in knowledge[nr]:
            possible.append(get_possible(k))

        discards = []
        for i, p in enumerate(possible):
            if playable(p, board):
                result = Action(Action.ActionType.PLAY, cnr=i)
            if discardable(p, board):
                discards.append(i)

        if discards and hints < 8 and not result:
            result = Action(Action.ActionType.DISCARD, cnr=random.choice(discards))

        playables = []
        useless = []
        discardables = []
        othercards = trash + board
        intentions: list[Intent | None] = [None for _ in range(handsize)]
        for i, h in enumerate(hands):
            if i != nr:
                for j, x in enumerate(h):
                    (col, n) = x
                    if board[col][1] + 1 == n:
                        playables.append((i, j))
                        intentions[j] = Intent.PLAY
                    if board[col][1] >= n:
                        useless.append((i, j))
                        if not intentions[j]:
                            intentions[j] = Intent.DISCARD
                    if n < 5 and (col, n) not in othercards:
                        discardables.append((i, j))
                        if not intentions[j]:
                            intentions[j] = Intent.CAN_DISCARD

        self.explanation.append(
            ["Intentions"] + list(map(format_intention, intentions))
        )

        if hints > 0:
            valid = []
            for c in Color:
                action = (Action.ActionType.HINT_COLOR, c)
                # print("HINT", COLORNAMES[c],)
                (isvalid, score, expl) = pretend(
                    action, knowledge[1 - nr], intentions, hands[1 - nr], board
                )
                self.explanation.append(
                    ["Prediction for: Hint Color " + c.display_name]
                    + list(map(format_intention, expl))
                )
                # print(isvalid, score)
                if isvalid:
                    valid.append((action, score))

            for r in range(5):
                r += 1
                action = (Action.ActionType.HINT_NUMBER, r)
                # print("HINT", r,)

                (isvalid, score, expl) = pretend(
                    action, knowledge[1 - nr], intentions, hands[1 - nr], board
                )
                self.explanation.append(
                    ["Prediction for: Hint Rank " + str(r)]
                    + list(map(format_intention, expl))
                )
                # print(isvalid, score)
                if isvalid:
                    valid.append((action, score))

            if valid and not result:
                valid.sort(key=lambda x: -x[1])
                # print(valid)
                (a, s) = valid[0]
                if a[0] == Action.ActionType.HINT_COLOR:
                    result = Action(Action.ActionType.HINT_COLOR, pnr=1 - nr, col=a[1])
                else:
                    result = Action(Action.ActionType.HINT_NUMBER, pnr=1 - nr, num=a[1])

        self.explanation.append(
            ["My Knowledge"] + list(map(format_knowledge, knowledge[nr]))
        )
        possible = [
            Action(Action.ActionType.DISCARD, cnr=i) for i in list(range(handsize))
        ]

        scores = list(
            map(lambda p: pretend_discard(p, knowledge[nr], board, trash), possible)
        )

        def format_term(x):
            (col, rank, n, prob, val) = x
            return (
                col.display_name
                + " "
                + str(rank)
                + " (%.2f%%): %.2f" % (prob * 100, val)
            )

        self.explanation.append(
            ["Discard Scores"]
            + list(
                map(
                    lambda x: "\n".join(map(format_term, x[2])) + "\n%.2f" % (x[1]),
                    scores,
                )
            )
        )
        scores.sort(key=lambda x: -x[1])
        if result:
            return result
        return scores[0][0]

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


class SelfIntentionalPlayer(Player):
    def __init__(self, name, pnr):
        super().__init__(name, pnr)
        self.gothint = None

    @override
    def reset(self) -> None:
        self.gothint = None

    def get_action(
        self, nr, hands, knowledge, trash, played, board, valid_actions, hints
    ):
        handsize = len(knowledge[0])
        possible = []
        result = None
        self.explanation = []
        self.explanation.append(["Your Hand:"] + list(map(f, hands[1 - nr])))
        action = []
        if self.gothint:
            (act, plr) = self.gothint
            if act.action_type == Action.ActionType.HINT_COLOR:
                for k in knowledge[nr]:
                    action.append(whattodo(k, sum(k[act.col]) > 0, board))
            elif act.action_type == Action.ActionType.HINT_NUMBER:
                for k in knowledge[nr]:
                    cnt = 0
                    for c in Color:
                        cnt += k[c][act.num - 1]
                    action.append(whattodo(k, cnt > 0, board))

        if action:
            self.explanation.append(
                ["What you want me to do"]
                + [
                    x.display_name if isinstance(x, Action.ActionType) else "Keep"
                    for x in action
                ]
            )
            for i, a in enumerate(action):
                if a == Action.ActionType.PLAY and (
                    not result or result.action_type == Action.ActionType.DISCARD
                ):
                    result = Action(Action.ActionType.PLAY, cnr=i)
                elif a == Action.ActionType.DISCARD and not result:
                    result = Action(Action.ActionType.DISCARD, cnr=i)

        self.gothint = None
        for k in knowledge[nr]:
            possible.append(get_possible(k))

        discards = []
        for i, p in enumerate(possible):
            if playable(p, board) and not result:
                result = Action(Action.ActionType.PLAY, cnr=i)
            if discardable(p, board):
                discards.append(i)

        if discards and hints < 8 and not result:
            result = Action(Action.ActionType.DISCARD, cnr=random.choice(discards))

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
                    if board[col][1] >= n:
                        useless.append((i, j))
                        if not intentions[j]:
                            intentions[j] = Intent.DISCARD
                    if n < 5 and (col, n) not in othercards:
                        discardables.append((i, j))
                        if not intentions[j]:
                            intentions[j] = Intent.CAN_DISCARD

        self.explanation.append(
            ["Intentions"] + list(map(format_intention, intentions))
        )

        if hints > 0:
            valid = []
            for c in Color:
                action = (Action.ActionType.HINT_COLOR, c)
                # print("HINT", COLORNAMES[c],)
                (isvalid, score, expl) = pretend(
                    action, knowledge[1 - nr], intentions, hands[1 - nr], board
                )
                self.explanation.append(
                    ["Prediction for: Hint Color " + c.display_name]
                    + list(map(format_intention, expl))
                )
                # print(isvalid, score)
                if isvalid:
                    valid.append((action, score))

            for r in range(5):
                r += 1
                action = (Action.ActionType.HINT_NUMBER, r)
                # print("HINT", r,)

                (isvalid, score, expl) = pretend(
                    action, knowledge[1 - nr], intentions, hands[1 - nr], board
                )
                self.explanation.append(
                    ["Prediction for: Hint Rank " + str(r)]
                    + list(map(format_intention, expl))
                )
                # print(isvalid, score)
                if isvalid:
                    valid.append((action, score))

            if valid and not result:
                valid.sort(key=lambda x: -x[1])
                # print(valid)
                (a, s) = valid[0]
                if a[0] == Action.ActionType.HINT_COLOR:
                    result = Action(Action.ActionType.HINT_COLOR, pnr=1 - nr, col=a[1])
                else:
                    result = Action(Action.ActionType.HINT_NUMBER, pnr=1 - nr, num=a[1])

        self.explanation.append(
            ["My Knowledge"] + list(map(format_knowledge, knowledge[nr]))
        )
        possible = [
            Action(Action.ActionType.DISCARD, cnr=i) for i in list(range(handsize))
        ]

        scores = list(
            map(lambda p: pretend_discard(p, knowledge[nr], board, trash), possible)
        )

        def format_term(x):
            (col, rank, _, prob, val) = x
            return (
                col.display_name
                + " "
                + str(rank)
                + " (%.2f%%): %.2f" % (prob * 100, val)
            )

        self.explanation.append(
            ["Discard Scores"]
            + list(
                map(
                    lambda x: "\n".join(map(format_term, x[2])) + "\n%.2f" % (x[1]),
                    scores,
                )
            )
        )
        scores.sort(key=lambda x: -x[1])
        if result:
            return result
        return scores[0][0]

    def inform(self, action, player, game):
        if action.pnr == self.pnr and action.action_type in {
            Action.ActionType.HINT_COLOR,
            Action.ActionType.HINT_NUMBER,
        }:
            self.gothint = (action, player)


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
        possible = []

        self.gothint = None
        for k in knowledge[nr]:
            possible.append(get_possible(k))

        discards = []
        plays = []
        for i, p in enumerate(possible):
            if playable(p, board):
                plays.append(i)
            if discardable(p, board):
                discards.append(i)

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

        if hints > 0:
            valid = []
            for c in Color:
                action = (Action.ActionType.HINT_COLOR, c)
                # print("HINT", COLORNAMES[c],)
                (isvalid, score) = pretend(
                    action, knowledge[1 - nr], intentions, hands[1 - nr], board
                )
                # print(isvalid, score)
                if isvalid:
                    valid.append((action, score))

            for r in range(5):
                r += 1
                action = (Action.ActionType.HINT_NUMBER, r)
                # print("HINT", r,)
                (isvalid, score) = pretend(
                    action, knowledge[1 - nr], intentions, hands[1 - nr], board
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


def format_card(x):
    (col, num) = x
    return col.display_name + " " + str(num)


def format_hand(hand):
    return ", ".join(list(map(format_card, hand)))


class Game:
    players: Sequence[Player]

    def __init__(self, players, log=sys.stdout, format=0):
        self.players = players
        self.hits = 3
        self.hints = 8
        self.current_player = 0
        self.board = [(c, 0) for c in Color]
        self.played = []
        self.deck = make_deck()
        self.extra_turns = 0
        self.hands = []
        self.knowledge = []
        self.make_hands()
        self.trash = []
        self.log = log
        self.turn = 1
        self.format = format
        self.dopostsurvey = False
        self.study = False
        if self.format:
            print(self.deck, file=self.log)

    def make_hands(self):
        handsize = 4
        if len(self.players) < 4:
            handsize = 5
        for i, p in enumerate(self.players):
            self.hands.append([])
            self.knowledge.append([])
            for j in list(range(handsize)):
                self.draw_card(i)

    def draw_card(self, pnr=None):
        if pnr is None:
            pnr = self.current_player
        if not self.deck:
            return
        self.hands[pnr].append(self.deck[0])
        self.knowledge[pnr].append(initial_knowledge())
        del self.deck[0]

    def perform(self, action: Action):
        for p in self.players:
            p.inform(action, self.current_player, self)
        if self.format:
            print(
                "MOVE:",
                self.current_player,
                action.action_type,
                action.cnr,
                action.pnr,
                action.col,
                action.num,
                file=self.log,
            )
        if action.action_type == Action.ActionType.HINT_COLOR:
            assert action.col is not None
            assert action.pnr is not None

            self.hints -= 1
            print(
                self.players[self.current_player].name,
                "hints",
                self.players[action.pnr].name,
                "about all their",
                action.col.display_name,
                "cards",
                "hints remaining:",
                self.hints,
                file=self.log,
            )
            print(
                self.players[action.pnr].name,
                "has",
                format_hand(self.hands[action.pnr]),
                file=self.log,
            )
            for (col, num), knowledge in zip(
                self.hands[action.pnr], self.knowledge[action.pnr]
            ):
                if col == action.col:
                    for i, k in enumerate(knowledge):
                        if i != col:
                            for i in range(len(k)):
                                k[i] = 0
                else:
                    for i in range(len(knowledge[action.col])):
                        knowledge[action.col][i] = 0
        elif action.action_type == Action.ActionType.HINT_NUMBER:
            assert action.num is not None
            assert action.pnr is not None

            self.hints -= 1
            print(
                self.players[self.current_player].name,
                "hints",
                self.players[action.pnr].name,
                "about all their",
                action.num,
                "hints remaining:",
                self.hints,
                file=self.log,
            )
            print(
                self.players[action.pnr].name,
                "has",
                format_hand(self.hands[action.pnr]),
                file=self.log,
            )
            for (col, num), knowledge in zip(
                self.hands[action.pnr], self.knowledge[action.pnr]
            ):
                if num == action.num:
                    for k in knowledge:
                        for i in range(len(COUNTS)):
                            if i + 1 != num:
                                k[i] = 0
                else:
                    for k in knowledge:
                        k[action.num - 1] = 0
        elif action.action_type == Action.ActionType.PLAY:
            (col, num) = self.hands[self.current_player][action.cnr]
            print(
                self.players[self.current_player].name,
                "plays",
                format_card((col, num)),
                file=self.log,
            )
            if self.board[col][1] == num - 1:
                self.board[col] = (col, num)
                self.played.append((col, num))
                if num == 5:
                    self.hints += 1
                    self.hints = min(self.hints, 8)
                print(
                    "successfully! Board is now", format_hand(self.board), file=self.log
                )
            else:
                self.trash.append((col, num))
                self.hits -= 1
                print("and fails. Board was", format_hand(self.board), file=self.log)
            del self.hands[self.current_player][action.cnr]
            del self.knowledge[self.current_player][action.cnr]
            self.draw_card()
            print(
                self.players[self.current_player].name,
                "now has",
                format_hand(self.hands[self.current_player]),
                file=self.log,
            )
        else:
            self.hints += 1
            self.hints = min(self.hints, 8)
            self.trash.append(self.hands[self.current_player][action.cnr])
            print(
                self.players[self.current_player].name,
                "discards",
                format_card(self.hands[self.current_player][action.cnr]),
                file=self.log,
            )
            print("trash is now", format_hand(self.trash), file=self.log)
            del self.hands[self.current_player][action.cnr]
            del self.knowledge[self.current_player][action.cnr]
            self.draw_card()
            print(
                self.players[self.current_player].name,
                "now has",
                format_hand(self.hands[self.current_player]),
                file=self.log,
            )

    def valid_actions(self):
        valid = []
        for i in range(len(self.hands[self.current_player])):
            valid.append(Action(Action.ActionType.PLAY, cnr=i))
            valid.append(Action(Action.ActionType.DISCARD, cnr=i))
        if self.hints > 0:
            for i, p in enumerate(self.players):
                if i != self.current_player:
                    for col in set(list(map(lambda x: x[0], self.hands[i]))):
                        valid.append(
                            Action(Action.ActionType.HINT_COLOR, pnr=i, col=col)
                        )
                    for num in set(list(map(lambda x: x[1], self.hands[i]))):
                        valid.append(
                            Action(Action.ActionType.HINT_NUMBER, pnr=i, num=num)
                        )
        return valid

    def run(self, turns=-1):
        for p in self.players:
            p.reset()
        self.turn = 1
        while not self.done() and (turns < 0 or self.turn < turns):
            self.turn += 1
            if not self.deck:
                self.extra_turns += 1
            hands = []
            for i, h in enumerate(self.hands):
                if i == self.current_player:
                    hands.append([])
                else:
                    hands.append(h)
            action = self.players[self.current_player].get_action(
                self.current_player,
                hands,
                self.knowledge,
                self.trash,
                self.played,
                self.board,
                self.valid_actions(),
                self.hints,
            )
            self.perform(action)
            self.current_player += 1
            self.current_player %= len(self.players)
        print("Game done, hits left:", self.hits, file=self.log)
        points = self.score()
        print("Points:", points, file=self.log)
        return points

    def score(self):
        return sum(list(map(lambda x: x[1], self.board)))

    def single_turn(self):
        if not self.done():
            if not self.deck:
                self.extra_turns += 1
            hands = []
            for i, h in enumerate(self.hands):
                if i == self.current_player:
                    hands.append([])
                else:
                    hands.append(h)
            action = self.players[self.current_player].get_action(
                self.current_player,
                hands,
                self.knowledge,
                self.trash,
                self.played,
                self.board,
                self.valid_actions(),
                self.hints,
            )
            self.perform(action)
            self.current_player += 1
            self.current_player %= len(self.players)

    def external_turn(self, action):
        if not self.done():
            if not self.deck:
                self.extra_turns += 1
            self.perform(action)
            self.current_player += 1
            self.current_player %= len(self.players)

    def done(self):
        if self.extra_turns == len(self.players) or self.hits == 0:
            return True
        for col, num in self.board:
            if num != 5:
                return False
        return True

    def finish(self):
        if self.format:
            print("Score", self.score(), file=self.log)
            self.log.close()


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
                g = Game(players, NullStream())
                t0 = time.time()
                result.append(g.run())
                times.append(time.time() - t0)
                avgtimes.append(times[-1] * 1.0 / g.turn)
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

    n = 10000
    out = NullStream()
    if n < 3:
        out = sys.stdout
    pts = []
    for i in list(range(n)):
        if (i + 1) % 100 == 0:
            print("Starting game", i + 1)
        random.seed(i + 1)
        g = Game(players, out)
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
