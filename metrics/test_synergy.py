from metrics.post_move import SynergyMetric
from utils import Action


def test_two_player_synergy():
    synergy = SynergyMetric(2)

    synergy(Action(Action.ActionType.HINT_NUMBER), 0, 3)
    synergy(Action(Action.ActionType.HINT_NUMBER), 0, 3)
    synergy(Action(Action.ActionType.PLAY), 1, 3)
    synergy(Action(Action.ActionType.DISCARD), 1, 3)
    synergy(Action(Action.ActionType.PLAY), 2, 3)
    synergy(Action(Action.ActionType.PLAY), 3, 3)
    synergy(Action(Action.ActionType.HINT_COLOR), 3, 3)
    synergy(Action(Action.ActionType.PLAY), 3, 2)
    synergy(Action(Action.ActionType.HINT_NUMBER), 3, 2)
    synergy(Action(Action.ActionType.HINT_NUMBER), 3, 2)
    synergy(Action(Action.ActionType.PLAY), 4, 2)

    print(synergy._get_distribution())
    print(synergy.final_value)


if __name__ == "__main__":
    test_two_player_synergy()
