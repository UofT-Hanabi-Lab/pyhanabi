import random
from typing import Final


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
