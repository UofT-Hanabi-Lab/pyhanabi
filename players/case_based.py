import random
from dataclasses import dataclass
from typing import Final, override

from players import Player
from utils import (
    COUNTS,
    MAX_HINT_TOKENS,
    Action,
    Color,
    Intent,
    discardable,
    get_possible,
    hint_color,
    hint_rank,
    playable,
    potentially_discardable,
    potentially_playable,
    pretend_discard,
    whattodo,
)

PLAY: Final = Action.ActionType.PLAY
DISCARD: Final = Action.ActionType.DISCARD
HINT_COLOR: Final = Action.ActionType.HINT_COLOR
HINT_NUMBER: Final = Action.ActionType.HINT_NUMBER

PLAY_SCORE: Final = 3
DISCARD_SCORE: Final = 2
MAY_DISCARD_SCORE: Final = 1
REJECTED: Final = float("-inf")


def is_hint(action: Action) -> bool:
    return action.action_type in (HINT_COLOR, HINT_NUMBER)


def hint_to(action: Action | None, player: int) -> Action | None:
    """Return action if it is a hint to player, otherwise None."""
    if action is not None and is_hint(action) and action.pnr == player:
        return action
    return None


def identifies(hint: Action, card: tuple[Color, int]) -> bool:
    """Return True iff hint positively identifies a visible card."""
    col, rank = card
    if hint.action_type is HINT_COLOR:
        return col == hint.col
    return rank == hint.num


def was_identified(hint: Action, table: list[list[int]]) -> bool:
    """Return True iff hint positively identified a hidden card, from its knowledge."""
    if hint.action_type is HINT_COLOR:
        assert hint.col is not None
        return any(table[hint.col])
    assert hint.num is not None
    return any(row[hint.num - 1] for row in table)


def apply_hint(
    hint: Action, hand: list[tuple[Color, int]], knowledge: list[list[list[int]]]
) -> list[list[list[int]]]:
    if hint.action_type is HINT_COLOR:
        return [
            hint_color(table, hint.col, col == hint.col)
            for (col, _), table in zip(hand, knowledge)
        ]
    return [
        hint_rank(table, hint.num, rank == hint.num)
        for (_, rank), table in zip(hand, knowledge)
    ]


def is_expendable(card: tuple[Color, int], trash: list[tuple[Color, int]]) -> bool:
    """Another copy remains. Only for cards that are not useless."""
    return COUNTS[card[1] - 1] - trash.count(card) >= 2


def assign_goals(
    hand: list[tuple[Color, int]],
    board: list[tuple[Color, int]],
    trash: list[tuple[Color, int]],
) -> list[Intent | None]:
    """Goals I_i"""
    goals: list[Intent | None] = []
    for col, rank in hand:
        top = board[col][1]
        if rank == top + 1:
            goals.append(Intent.PLAY)
        elif rank <= top:
            goals.append(Intent.DISCARD)
        elif is_expendable((col, rank), trash):
            goals.append(Intent.CAN_DISCARD)
        else:
            goals.append(None)
    return goals


def predict(
    knowledge: list[list[list[int]]],
    touched: list[bool],
    board: list[tuple[Color, int]],
) -> list[Action.ActionType | None]:
    """
    PREDICT (Algorithm 1)
    Precondition: The hint is already applied to knowledge.
    """
    return [whattodo(table, hit, board) for table, hit in zip(knowledge, touched)]


def alignment_score(
    goals: list[Intent | None], predictions: list[Action.ActionType | None]
) -> float:
    """S (Algorithm 7)."""
    total = 0.0
    for goal, predicted in zip(goals, predictions):
        if predicted is PLAY and goal is not Intent.PLAY:
            return REJECTED
        if predicted is DISCARD and goal in (Intent.PLAY, None):
            return REJECTED
        if predicted is PLAY:
            total += PLAY_SCORE
        elif predicted is DISCARD:
            total += DISCARD_SCORE if goal is Intent.DISCARD else MAY_DISCARD_SCORE
    return total


def response_utility(
    hint: Action,
    action: Action,
    knowledge: list[list[list[int]]],
    board: list[tuple[Color, int]],
    trash: list[tuple[Color, int]],
) -> int:
    """U (Algorithm 6). knowledge is A's own hand."""
    if action.action_type not in (PLAY, DISCARD):
        return 0
    assert action.cnr is not None
    table = knowledge[action.cnr]
    if not was_identified(hint, table):
        return 0
    possible = get_possible(table)
    if action.action_type is PLAY:
        return PLAY_SCORE if potentially_playable(possible, board) else 0
    if potentially_discardable(possible, board):
        return DISCARD_SCORE
    if any(is_expendable(card, trash) for card in possible):
        return MAY_DISCARD_SCORE
    return 0


def outcomes(
    action: Action,
    table: list[list[int]],
    board: list[tuple[Color, int]],
    trash: list[tuple[Color, int]],
) -> list[tuple[int, list[tuple[Color, int]], list[tuple[Color, int]]]]:
    """(weight, board, trash) for each identity a played or discarded card may have."""
    results = []
    for col in Color:
        for i, count in enumerate(table[col]):
            if count <= 0:
                continue
            card = (col, i + 1)
            if action.action_type is PLAY and board[col][1] + 1 == card[1]:
                new_board = board[:]
                new_board[col] = card
                results.append((count, new_board, trash))
            else:
                results.append((count, board, trash + [card]))
    return results


@dataclass(frozen=True)
class _Turn:
    a: int
    b: int
    c: int
    hands: list[list[tuple[Color, int]]]
    knowledge: list[list[list[list[int]]]]
    trash: list[tuple[Color, int]]
    board: list[tuple[Color, int]]
    tokens: int
    legal: list[Action]


@dataclass
class _Candidate:
    action: Action
    utility: float = 0.0  # sum of U over the hints A received
    plan: float = 0.0  # S(I_B, A^_B) after the action
    hint_score: float = 0.0  # H, used only to rank hints

    @property
    def objective(self) -> float:
        return self.utility + self.plan


class CaseBasedPlayer(Player):
    def __init__(self, name: str, pnr: int):
        super().__init__(name, pnr)
        self._last_actions: dict[int, Action] = {}  # a_B and a_C
        self.case: str | None = None
        self.valid_hints: list[tuple[str | int, int, float]] = []
        self.redun_hints: list[tuple[str | int, int, float]] = []

    @override
    def reset(self) -> None:
        self._last_actions = {}
        self.case = None
        self.valid_hints = []
        self.redun_hints = []

    # Read by the game's JSON log.
    def get_valid_hints(self):
        return self.valid_hints

    def get_redundant_hints(self):
        return self.redun_hints

    def get_critical_hints(self):
        return []

    @override
    def inform(self, action: Action, player: int, game) -> None:
        if player == self.pnr:
            self._last_actions = {}
        else:
            self._last_actions[player] = action

    @override
    def get_action(
        self,
        nr,
        hands,
        knowledge,
        trash,
        played,
        board,
        valid_actions,
        hints,
        lives=None,
        deck_size=None,
    ) -> Action:
        """Algorithm 8."""
        num_players = len(knowledge)
        turn = _Turn(
            a=nr,
            b=(nr + 1) % num_players,
            c=(nr - 1) % num_players,
            hands=hands,
            knowledge=knowledge,
            trash=trash,
            board=board,
            tokens=hints,
            legal=valid_actions,
        )
        self.case = None
        self.valid_hints = []
        self.redun_hints = []
        self.explanation = []

        # Lines 2-4
        for action in turn.legal:
            if action.action_type is PLAY:
                possible = get_possible(knowledge[nr][action.cnr])
                if possible and playable(possible, board):
                    self.explanation.append(["Certainly playable", str(action)])
                    return action

        # Lines 5-21
        self.case, received, plan = self._classify(turn)
        candidates, redundant = self._candidates(turn, received, plan)
        self._explain(candidates)
        if not candidates:
            # Full hint bank and no intentional hint: Algorithm 2, lines 19-21.
            return random.choice(redundant or [a for a in turn.legal if is_hint(a)])
        best = max(candidate.objective for candidate in candidates)
        top = [candidate for candidate in candidates if candidate.objective == best]

        # Lines 22-23, also used to break ties
        return self._baseline_choice(turn, top)

    def _classify(self, turn: _Turn) -> tuple[str, list[Action], Action | None]:
        """Returns (case, hints A received, C's pending hint to B)."""
        a_b = self._last_actions.get(turn.b)
        a_c = self._last_actions.get(turn.c) if turn.c != turn.b else None
        b_to_a = hint_to(a_b, turn.a)
        c_to_a = hint_to(a_c, turn.a)
        c_to_b = hint_to(a_c, turn.b)

        if b_to_a and c_to_a:
            return "1a", [b_to_a, c_to_a], None
        if b_to_a and c_to_b:
            return "1b", [b_to_a], c_to_b
        if b_to_a:
            return "1c", [b_to_a], None
        if c_to_a:
            return "2a", [c_to_a], None
        if c_to_b:
            return "2b", [], c_to_b
        return "2c", [], None

    def _candidates(
        self, turn: _Turn, received: list[Action], plan: Action | None
    ) -> tuple[list[_Candidate], list[Action]]:
        """Returns (candidates with objective terms, redundant hints)."""
        own = turn.knowledge[turn.a]
        candidates = []
        for action in turn.legal:
            kind = action.action_type
            if kind is DISCARD and turn.tokens >= MAX_HINT_TOKENS:
                continue
            if kind in (PLAY, DISCARD):
                utility = sum(
                    response_utility(hint, action, own, turn.board, turn.trash)
                    for hint in received
                )
                # Plays with no hint behind them are not candidates.
                if kind is DISCARD or utility > 0:
                    candidates.append(_Candidate(action, utility=utility))
        hints, redundant = self._intentional_hints(turn, plan)
        candidates.extend(hints)

        if plan is not None:
            for candidate in candidates:
                candidate.plan = self._plan_after(turn, plan, candidate.action)
            # If S is -inf whatever A does, it gives no guidance.
            if all(candidate.plan == REJECTED for candidate in candidates):
                for candidate in candidates:
                    candidate.plan = 0.0
        return candidates, redundant

    def _plan_after(self, turn: _Turn, plan: Action, action: Action) -> float:
        """S(I_B, A^_B) for C's hint ``plan`` in the state resulting from ``action``."""
        hand = turn.hands[turn.b]
        knowledge = turn.knowledge[turn.b]
        states = [(1, turn.board, turn.trash)]
        if is_hint(action):
            if action.pnr == turn.b:
                knowledge = apply_hint(action, hand, knowledge)
        else:
            assert action.cnr is not None
            table = turn.knowledge[turn.a][action.cnr]
            states = outcomes(action, table, turn.board, turn.trash) or states

        touched = [identifies(plan, card) for card in hand]
        weight_of: dict[float, int] = {}
        for weight, board, trash in states:
            value = alignment_score(
                assign_goals(hand, board, trash), predict(knowledge, touched, board)
            )
            weight_of[value] = weight_of.get(value, 0) + weight
        # A's card is hidden: take the most likely value, the worse one on ties.
        return max(weight_of, key=lambda value: (weight_of[value], -value))

    def _intentional_hints(
        self, turn: _Turn, plan: Action | None
    ) -> tuple[list[_Candidate], list[Action]]:
        """Returns (qualifying hints scored with H, redundant hints)."""
        qualifying: list[_Candidate] = []
        redundant: list[Action] = []
        if turn.tokens == 0:
            return qualifying, redundant

        for hint in turn.legal:
            if not is_hint(hint):
                continue
            assert hint.pnr is not None
            hand = turn.hands[hint.pnr]
            before = turn.knowledge[hint.pnr]
            after = apply_hint(hint, hand, before)
            label = hint.num if hint.col is None else hint.col.display_name
            assert label is not None
            if not any(
                    identifies(hint, card) and new != old
                    for card, old, new in zip(hand, before, after)
            ):
                redundant.append(hint)
                self.redun_hints.append((label, hint.pnr, 0))
                continue

            # A hint to B is scored together with C's pending hint to B.
            pending = [plan] if plan is not None and hint.pnr == turn.b else []
            score_before = self._alignment(turn, hand, before, pending)
            score_after = self._alignment(turn, hand, after, pending + [hint])
            if score_after > score_before:
                gain = score_after - score_before
                qualifying.append(_Candidate(hint, hint_score=gain))
                self.valid_hints.append((label, hint.pnr, score_after))
        return qualifying, redundant

    def _alignment(
        self,
        turn: _Turn,
        hand: list[tuple[Color, int]],
        knowledge: list[list[list[int]]],
        pending: list[Action],
    ) -> float:
        """S(I_i, A^_i) for a partner's response to its ``pending`` hints."""
        touched = [any(identifies(hint, card) for hint in pending) for card in hand]
        return alignment_score(
            assign_goals(hand, turn.board, turn.trash),
            predict(knowledge, touched, turn.board),
        )

    def _baseline_choice(self, turn: _Turn, top: list[_Candidate]) -> Action:
        """Baseline priority sequence, restricted to ``top``."""
        own = turn.knowledge[turn.a]

        responses = [candidate for candidate in top if candidate.utility > 0]
        if responses:
            return max(responses, key=lambda candidate: candidate.utility).action

        discards = [c.action for c in top if c.action.action_type is DISCARD]
        useless = []
        for action in discards:
            assert action.cnr is not None
            possible = get_possible(own[action.cnr])
            if possible and discardable(possible, turn.board):
                useless.append(action)
        if useless:
            return random.choice(useless)

        hints = [candidate for candidate in top if is_hint(candidate.action)]
        if hints:
            best = max(candidate.hint_score for candidate in hints)
            return random.choice([c.action for c in hints if c.hint_score == best])

        # pretend_discard returns the negated expected loss.
        return max(
            discards,
            key=lambda action: pretend_discard(action, own, turn.board, turn.trash)[1],
        )

    def _explain(self, candidates: list[_Candidate]) -> None:
        self.explanation.append(["Case", self.case])
        self.explanation.append(["Candidate"] + [str(c.action) for c in candidates])
        self.explanation.append(["Utility U"] + [c.utility for c in candidates])
        self.explanation.append(["Plan S"] + [c.plan for c in candidates])
        self.explanation.append(["Hint score H"] + [c.hint_score for c in candidates])
