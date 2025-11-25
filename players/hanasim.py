from typing import override

from hana_sim import PlayerName  # type: ignore

from players import Player
from utils import Action


class HanaSimPlayer(Player):
    _hana_sim_name: PlayerName

    @override
    def __init__(self, name: str | PlayerName, pnr: int, hand_size: int = 5):
        super().__init__(str(name), pnr, hand_size)
        if isinstance(name, PlayerName):
            self._hana_sim_name = name

    @property
    def hana_sim_name(self) -> PlayerName:
        return self._hana_sim_name

    @override
    def get_action(
        self, nr, hands, knowledge, trash, played, board, valid_actions, hint_tokens
    ) -> Action:
        raise TypeError("get_action should never be called on a HanaSim player")
