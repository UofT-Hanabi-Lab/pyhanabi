import random
from typing import Final

from typing import TYPE_CHECKING
from utils import Action

# HACK: Player.inform is tightly coupled to AbstractGame
#   to fix: extract an interface from AbstractGame to invert the two-way dependency
if TYPE_CHECKING:
    from game import AbstractGame


class Player:
    def __init__(self, name: str, pnr: int, hand_size: int = 5):
        self.name: str = name
        self.pnr: int = pnr
        self._hand_size: Final[int] = hand_size

        self.explanation: list = []

    def reset(self) -> None:
        """
        Sets the player's state back to the initial state, as though it has never played
        a game.
        """
        pass

    def get_action(
        self, nr, hands, knowledge, trash, played, board, valid_actions, hint_tokens
    ) -> Action:
        return random.choice(valid_actions)

    def inform(self, action: Action, acting_player: int, game: "AbstractGame"):
        pass

    def get_explanation(self):
        return self.explanation
