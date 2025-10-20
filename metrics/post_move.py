from abc import ABC, abstractmethod
from collections import deque, Counter
from typing import override

from dit import Distribution  # type: ignore
from dit.pid import PID_CCS  # type: ignore

from utils import Action


class PostMoveMetric(ABC):
    """Abstract base class for metrics evaluated after each move."""

    @abstractmethod
    def __call__(self, last_action: Action, **kwargs) -> int | float:
        raise NotImplementedError


class SynergyMetric(PostMoveMetric):
    """
    Estimate the synergistic information for one game.

    The final value is solely dependent on the moves taken within a completed game.
    The final value can be retrieved from the `final_value` property.
    """

    _window: deque[Action]
    """Moving window containing the last window_size actions"""

    _counts: Counter[str]
    """
    The number of occurrences of each information state observed in the game

    e.g. The value at key "001" is the number of times in the game that the sequence of
    actions encoded as "00" and the outcome encoded as "1" occurs.
    """

    _prev_lives_remaining: int
    """Lives remaining before the most recent action is taken"""

    _prev_score: int
    """Game score before the most recent action is taken"""

    def __init__(self, window_size: int) -> None:
        self._window = deque(maxlen=window_size)
        self._counts = Counter()
        self._prev_score = 0
        self._prev_lives_remaining = 3

    @override
    def __call__(
        self,
        last_action: Action,
        score: int | None = None,
        lives: int | None = None,
        **kwargs,
    ):
        if score is None or lives is None:
            raise ValueError(
                "Unable to compute synergy: score and lives cannot be None"
            )

        self._window.append(last_action)

        # only start counting after window_size actions have occurred
        if len(self._window) == self._window.maxlen:
            self._counts[self._encode_window(score, lives)] += 1

        self._prev_score = score
        self._prev_lives_remaining = lives

    def _encode_window(self, score: int, lives: int) -> str:
        encoding: str = ""
        for action in self._window:
            encoding += self._encode_action(action)
        encoding += self._encode_outcome(score, lives)
        return encoding

    @staticmethod
    def _encode_action(action: Action) -> str:
        match action.action_type:
            case Action.ActionType.PLAY:
                return "00"
            case Action.ActionType.DISCARD:
                return "01"
            case Action.ActionType.HINT_COLOR | Action.ActionType.HINT_NUMBER:
                return "10"
            case _:
                raise ValueError(f"Unknown action type: {action.action_type}")

    def _encode_outcome(self, score: int, lives: int) -> str:
        if self._prev_lives_remaining > lives:
            # a life was lost by the last action
            return "0"
        elif self._prev_score < score:
            # a point was gained by the last action
            return "1"
        else:
            return "2"

    @property
    def final_value(self) -> float:
        assert self._window.maxlen is not None
        return PID_CCS(self._get_distribution())[
            tuple((n,) for n in range(self._window.maxlen))
        ]

    def _get_distribution(self) -> Distribution:
        outcomes: list[str] = []
        pmf: list[float] = []

        for state, count in self._counts.items():
            outcomes.append(state)
            pmf.append(count / self._counts.total())

        return Distribution(outcomes, pmf)
