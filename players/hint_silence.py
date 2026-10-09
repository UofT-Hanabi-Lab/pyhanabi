"""V12 (Hint Silence Tracking).

Subclass of the baseline full intentional agent (SelfIntentionalPlayer
version 0). The turn order is that version unchanged. The only decision
change is the discard-loss heuristic: identities that are already useless
or expendable get a small discount from a per-card silence counter.

Useless and expendable follow pretend_discard's branches in utils.py:
  - useless: the firework is already at least this rank (or the color is dead)
  - expendable: more than one copy of that identity remains in the knowledge
    count (the multi-copy branch). Rank 5s never land here.
The one-copy branch (a possible last copy of a still-needed card) is not
adjusted.
"""

import copy

from players.self_intentional import SelfIntentionalPlayer
from utils import (
    Action,
    Color,
    MAX_HINT_TOKENS,
    f,
)


class HintSilencePlayer(SelfIntentionalPlayer):
    def __init__(self, name, pnr, eta=0.9, lambda_=0.5):
        super().__init__(name, pnr, version=0)
        self.eta = eta
        self.lam = lambda_
        self._silence = [0.0] * self._hand_size
        self.heuristic_discards = 0
        self.discard_flips = 0
        self.n_values: list[float] = []
        self._baseline_cnr = None

    def reset(self) -> None:
        super().reset()
        self._silence = [0.0] * self._hand_size
        self.heuristic_discards = 0
        self.discard_flips = 0
        self.n_values = []
        self._baseline_cnr = None

    def inform(self, action, player, game):
        super().inform(action, player, game)
        if action.action_type in {
            Action.ActionType.HINT_COLOR,
            Action.ActionType.HINT_NUMBER,
        } and action.pnr == self.pnr:
            # Only hints aimed at us. Positive slots are the ones the hint
            # says match; everyone else has been passed over.
            cards = _own_hand(game, self.pnr)
            for i, card in enumerate(cards):
                if i >= len(self._silence):
                    break
                if not _hint_matches(card, action):
                    self._silence[i] += 1
        elif player == self.pnr and action.action_type in {
            Action.ActionType.PLAY,
            Action.ActionType.DISCARD,
        }:
            # Same shift as the knowledge table: drop that slot, new card at
            # the end starts at 0. Index follows the mental-state slot the
            # discard heuristic reads, which is action.cnr.
            del self._silence[action.cnr]
            self._silence.append(0.0)

    def get_action(
        self, nr, hands, knowledge, trash, played, board, valid_actions, hints, lives, deck_size
    ):
        assert len(self._silence) == len(knowledge[nr]), (
            len(self._silence),
            len(knowledge[nr]),
        )
        self._silence = [self.eta * n for n in self._silence]

        # Version 0 turn, unchanged. Copied here only so we can tell a
        # heuristic discard from a discard chosen earlier in the turn.
        num_players = len(knowledge)
        possible = []
        result = None
        self.explanation = []
        self.explanation.append(["Your Hand:"] + list(map(f, hands[1 - nr])))
        action_buf = []
        self.valid_hints = []
        self.redun_hints = []

        if self.got_hint:
            result = self.received_hint(nr, knowledge, board, hints, result, action_buf)
        if not result:
            result = self.play_or_discard(nr, knowledge, board, hints, possible, result)
        redundant_hints = []
        if not result:
            result, redundant_hints = self.give_intentional_hint(
                nr, hands, knowledge, trash, board, hints, num_players, result
            )
        if hints == MAX_HINT_TOKENS and not result:
            if redundant_hints:
                result = self.give_redundant_hint(redundant_hints)
            else:
                result = self.give_random_hint(valid_actions)

        scores = self.discard_card(nr, knowledge, trash, board)
        if result:
            assert result in valid_actions
            return result

        chosen = scores[0][0]
        assert chosen in valid_actions
        self.heuristic_discards += 1
        self.n_values.extend(self._silence)
        if chosen.cnr != self._baseline_cnr:
            self.discard_flips += 1
        return chosen

    def discard_card(self, nr, knowledge, trash, board):
        possible = [
            Action(Action.ActionType.DISCARD, cnr=i) for i in range(self._hand_size)
        ]
        baseline = [
            _discard_expected(p, knowledge[nr], board, trash, 0.0, 0.0) for p in possible
        ]
        adjusted = [
            _discard_expected(p, knowledge[nr], board, trash, self._silence[p.cnr], self.lam)
            for p in possible
        ]
        baseline_sorted = sorted(baseline, key=lambda x: -x[1])
        self._baseline_cnr = baseline_sorted[0][0].cnr
        adjusted.sort(key=lambda x: -x[1])
        return adjusted


def _own_hand(game, pnr):
    obs = getattr(game, "_obs", None)
    if obs is not None:
        cmap = game.hanasim_colour_map
        return [(cmap[color], rank) for color, rank in obs.hands[pnr]]
    return list(game.hands[pnr])


def _hint_matches(card, action) -> bool:
    col, rank = card
    if action.action_type == Action.ActionType.HINT_COLOR:
        return col == action.col
    return rank == action.num


def _discard_expected(act, knowledge, board, trash, silence, lam, hint_value=0.5):
    """pretend_discard, plus lam * silence * prob on useless and expendable identities.

    silence is N(card). lam == 0 leaves the baseline value unchanged.
    """
    which = copy.deepcopy(knowledge[act.cnr])
    for col, num in trash:
        if which[col][num - 1]:
            which[col][num - 1] -= 1
    for col in Color:
        for i in range(board[col][1]):
            if which[col][i]:
                which[col][i] -= 1
    possibilities = sum(map(sum, which))
    expected = 0.0
    terms = []
    # Baseline calls pretend_discard with ignore_dead=False, which sets every
    # dead-color cap to 5. Useless is then "firework already >= this rank".
    dead_colors = {color: 5 for color in Color}
    for col in Color:
        for i, cnt in enumerate(which[col]):
            rank = i + 1
            if cnt <= 0:
                continue
            prob = cnt * 1.0 / possibilities
            useless = board[col][1] >= rank or rank > dead_colors[col]
            if useless:
                contribution = prob * hint_value
                if lam:
                    contribution += lam * silence * prob
                expected += contribution
                terms.append((col, rank, cnt, prob, contribution))
            else:
                dist = rank - board[col][1]
                if cnt > 1:
                    # Expendable: another copy is still in the knowledge count.
                    value = prob * (6 - rank) / (dist * dist)
                else:
                    # One copy left. Potentially critical. Unchanged.
                    value = 6 - rank
                if rank == 5:
                    value += hint_value
                value *= prob
                if lam and cnt > 1:
                    value -= lam * silence * prob
                expected -= value
                terms.append((col, rank, cnt, prob, -value))
    return (act, expected, terms)
