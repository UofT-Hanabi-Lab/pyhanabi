import random
import copy
from enum import Enum, IntEnum, unique


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
        self.cnr = cnr  # card number (i.e. index)

    def __str__(self):
        if self.action_type == Action.ActionType.HINT_COLOR:
            assert self.col is not None
            return (
                "hints player "
                + str(self.pnr)
                + " about all their "
                + self.col.display_name
                + " cards"
            )
        if self.action_type == Action.ActionType.HINT_NUMBER:
            return "hints player " + str(self.pnr) + " about all their " + str(self.num)
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


class Log:
    outfile: str
    num_turns: int

    def __init__(self, outfile):
        """
        Outfile must be the file path from the top level directory pyhanabi.
        """
        self.outfile = outfile
        self.num_turns = 0

    def log_game_start(self, deck):
        with open(self.outfile, "a") as file:
            file.write(f"NEW: starting a new game with the following deck:\n{deck}\n")

    def log_action(self, pnr: int, action: Action):
        self.num_turns += 1
        with open(self.outfile, "a") as file:
            file.write(f"Turn {self.num_turns}: Player {pnr} {action.__str__()}\n")


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


def format_card(x):
    (col, num) = x
    return col.display_name + " " + str(num)


def format_hand(hand):
    return ", ".join(list(map(format_card, hand)))


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
    """
    Given a card identity, create a matrix representation where the only
    possible identity is the input's identity.
    """
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


def get_possible(knowledge):
    """
    Get all the possible identities for a card given the current knowledge.
    """
    result = []
    for col in Color:
        for i, cnt in enumerate(knowledge[col]):
            if cnt > 0:
                result.append((col, i + 1))
    return result


def playable(possible, board, dead_colors=None):
    """
    Return True iff every possible identity for this card is playable.
    """
    if dead_colors is None:
        dead_colors = {color: 5 for color in Color}

    for col, nr in possible:
        if board[col][1] + 1 != nr or nr > dead_colors[col]:
            return False
    return True


def potentially_playable(possible, board, dead_colors=None):
    """
    Return True iff at least one possible identity for this card is playable.
    """
    if dead_colors is None:
        dead_colors = {color: 5 for color in Color}

    for col, nr in possible:
        if board[col][1] + 1 == nr and nr <= dead_colors[col]:
            return True
    return False


def discardable(possible, board, dead_colors=None):
    """
    Return True iff every possible identity for this card is discardable.
    """
    if dead_colors is None:
        dead_colors = {color: 5 for color in Color}

    for col, nr in possible:
        if board[col][1] < nr and nr <= dead_colors[col]:
            return False
    return True


def potentially_discardable(possible, board, dead_colors=None):
    """
    Return True iff at least one possible identity for this card is discardable.
    """
    if dead_colors is None:
        dead_colors = {color: 5 for color in Color}

    for col, nr in possible:
        if board[col][1] >= nr or nr > dead_colors[col]:
            return True
    return False


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


def whattodo(knowledge, pointed, board, dead_colors=None) -> Action.ActionType | None:
    possible = get_possible(knowledge)
    play = potentially_playable(possible, board, dead_colors)
    discard = potentially_discardable(possible, board, dead_colors)

    if play and pointed:
        return Action.ActionType.PLAY
    if discard and pointed:
        return Action.ActionType.DISCARD
    return None


def pretend(action, knowledge, intentions, hand, board, trash, ignore_dead=False):
    """
    Pretend to give a hint and evaluates its effect on hand knowledge,
    and the score of the game.
    - if no cards match the hint, the hint is invalid
    - tracks how much this hint would improve the player's future moves
    - predict what each player would likely do with their cards after receiving the hint
    """
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

    if ignore_dead:
        dead_colors = highest_playable_cards(board, trash)
    else:
        dead_colors = None

    score = 0
    predictions: list[Intent | None] = []
    pos = False
    for i, c, k, p in zip(intentions, hand, newknowledge, positive):
        predicted_action = whattodo(k, p, board, dead_colors)
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


def pretend_discard(act, knowledge, board, trash, ignore_dead=False, hint_value=0.5):
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
    if ignore_dead:
        dead_colors = highest_playable_cards(board, trash)
    else:
        dead_colors = {color: 5 for color in Color}
    for col in Color:
        for i, cnt in enumerate(which[col]):
            rank = i + 1
            if cnt > 0:
                prob = cnt * 1.0 / possibilities
                if board[col][1] >= rank or rank > dead_colors[col]:
                    expected += prob * hint_value
                    terms.append((col, rank, cnt, prob, prob * hint_value))
                else:
                    dist = rank - board[col][1]
                    if cnt > 1:
                        value = prob * (6 - rank) / (dist * dist)
                    else:
                        value = 6 - rank
                    if rank == 5:
                        value += hint_value
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


def highest_playable_cards(board, trash):
    """
    Identifies "dead" colors. A dead color is defined as a color whose pile cannot
    be completed because all copies of a necessary card have been used (discarded).

    Returns a mapping of colors to the highest card that can still be played,
    given the current discard pile.
    """
    dead_colors = {}
    for col in Color:
        dead_colors[col] = 5  # Initialize all colors as possible to complete
        # For each color, find the highest rank that is still achievable
        for nr in range(board[col][1] + 1, 5 + 1):
            available = COUNTS[nr - 1]
            used = trash.count((col, nr))
            if available == used:
                dead_colors[col] = nr - 1
                break
    return dead_colors


class NullStream:
    def write(self, _):
        pass

    def flush(self):
        pass

    def writelines(self, _):
        pass
