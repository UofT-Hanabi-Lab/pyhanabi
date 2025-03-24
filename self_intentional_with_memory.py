import random
from typing import Sequence, override

from hanabi import (
    Player,
    whattodo,
    Color,
    format_intention,
    Action,
    get_possible,
    playable,
    discardable,
    pretend,
    format_knowledge,
    pretend_discard,
    f,
    Intent,
    Game,
)


def _intent_unchanged(old: Intent | None, new: Intent | None) -> bool:
    return old == new or (old == Intent.PLAY and new is None)


class SelfIntentionalPlayerWithMemory(Player):
    pnr: int
    got_hint: tuple[Action, int] | None
    _intents_conveyed: list[Intent | None]

    def __init__(self, name: str, pnr: int):
        super().__init__(name, pnr)
        self.got_hint = None
        self._intents_conveyed = [None for _ in range(self._hand_size)]

    @override
    def reset(self) -> None:
        self.got_hint = None
        self._intents_conveyed = [None for _ in range(self._hand_size)]

    def get_action(
        self, pnr: int, hands, knowledge, trash, played, board, valid_actions, hints
    ) -> Action:
        possible = []
        result = None
        self.explanation = []
        self.explanation.append(["Your Hand:"] + list(map(f, hands[1 - pnr])))
        action = []
        if self.got_hint:
            (act, plr) = self.got_hint
            if act.action_type == Action.ActionType.HINT_COLOR:
                assert act.col is not None
                for k in knowledge[pnr]:
                    action.append(whattodo(k, sum(k[act.col]) > 0, board))
            elif act.action_type == Action.ActionType.HINT_NUMBER:
                assert act.num is not None
                for k in knowledge[pnr]:
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

        self.got_hint = None
        for k in knowledge[pnr]:
            possible.append(get_possible(k))

        discards = []
        for i, p in enumerate(possible):
            if playable(p, board) and not result:
                result = Action(Action.ActionType.PLAY, cnr=i)
            if discardable(p, board):
                discards.append(i)

        if discards and hints < 8 and not result:
            result = Action(Action.ActionType.DISCARD, cnr=random.choice(discards))

        intentions = self.generate_intents(board, hands, pnr, trash)

        self.explanation.append(
            ["Intentions"] + list(map(format_intention, intentions))
        )

        if hints > 0:
            result = self.give_hint(board, hands, intentions, knowledge, pnr, result, trash)

        self.explanation.append(
            ["My Knowledge"] + list(map(format_knowledge, knowledge[pnr]))
        )
        possible = [
            Action(Action.ActionType.DISCARD, cnr=i)
            for i in list(range(self._hand_size))
        ]

        scores = list(
            map(lambda p: pretend_discard(p, knowledge[pnr], board, trash), possible)
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

    def generate_intents(self, board, hands, nr, trash) -> Sequence[Intent | None]:
        playables = []
        useless = []
        discardables = []
        othercards = trash + board
        intentions: list[Intent | None] = [None for _ in range(self._hand_size)]

        for i, h in enumerate(hands):
            if i != nr:
                for j, (col, n) in enumerate(h):
                    if board[col][1] + 1 == n:
                        playables.append((i, j))
                        intentions[j] = Intent.PLAY
                    elif board[col][1] >= n:
                        useless.append((i, j))
                        intentions[j] = Intent.DISCARD
                    elif n < 5 and (col, n) not in othercards:
                        discardables.append((i, j))
                        intentions[j] = Intent.CAN_DISCARD

        return intentions

    def give_hint(self, board, hands, intentions, knowledge, nr, result, trash) -> Action:
        valid: list[
            tuple[tuple[Action.ActionType, int | Color], int, list[int | None]]
        ] = []
        action: tuple[Action.ActionType, int | Color]
        for c in Color:
            action = (Action.ActionType.HINT_COLOR, c)
            (isvalid, score, expl) = pretend(
                action, knowledge[1 - nr], intentions, hands[1 - nr], board, trash
            )

            if isvalid and all(
                _intent_unchanged(self._intents_conveyed[i], expl[i])
                for i in range(len(self._intents_conveyed))
            ):
                isvalid = False
                score = 0
                expl = ["No new intentions"]

            self.explanation.append(
                ["Prediction for: Hint Color " + c.display_name]
                + list(map(format_intention, expl))
            )

            if isvalid:
                assert all(isinstance(x, Intent) or x is None for x in expl)
                valid.append((action, score, expl))
        for rank in range(5):
            rank += 1
            action = (Action.ActionType.HINT_NUMBER, rank)

            (isvalid, score, expl) = pretend(
                action, knowledge[1 - nr], intentions, hands[1 - nr], board, trash
            )

            if isvalid and all(
                _intent_unchanged(self._intents_conveyed[i], expl[i])
                for i in range(len(self._intents_conveyed))
            ):
                isvalid = False
                score = 0
                expl = ["No new intentions"]

            self.explanation.append(
                ["Prediction for: Hint Rank " + str(rank)]
                + list(map(format_intention, expl))
            )

            if isvalid:
                assert all(isinstance(x, Intent) or x is None for x in expl)
                valid.append((action, score, expl))
        if valid and not result:
            valid.sort(key=lambda x: x[1], reverse=True)
            (a, s, expl) = valid[0]

            # I assume that result will not be mutated after this block and in the calling code
            if a[0] == Action.ActionType.HINT_COLOR:
                assert isinstance(a[1], Color)
                result = Action(Action.ActionType.HINT_COLOR, pnr=1 - nr, col=a[1])
            else:
                result = Action(Action.ActionType.HINT_NUMBER, pnr=1 - nr, num=a[1])

            self._intents_conveyed = [
                self._intents_conveyed[i]
                if expl[i] is None and self._intents_conveyed[i] == Intent.PLAY
                else expl[i]
                for i in range(len(expl))
            ]
        return result

    def _rotate_intents(self, removed_cnr: int) -> None:
        for i in range(removed_cnr, len(self._intents_conveyed) - 1):
            self._intents_conveyed[i] = self._intents_conveyed[i + 1]
        self._intents_conveyed[-1] = None

    def inform(self, action: Action, player: int, game: Game) -> None:
        if (
            action.action_type in {Action.ActionType.PLAY, Action.ActionType.DISCARD}
            and player != self.pnr
        ):
            assert action.cnr is not None
            self._rotate_intents(action.cnr)

        elif action.pnr == self.pnr:
            self.got_hint = (action, player)
