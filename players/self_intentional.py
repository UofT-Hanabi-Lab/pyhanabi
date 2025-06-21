import random
from typing import override

from players import Player
from utils import (
    get_possible,
    playable,
    Action,
    discardable,
    Intent,
    Color,
    pretend,
    f,
    format_intention,
    format_knowledge,
    pretend_discard,
    whattodo,
)


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
                    action, knowledge[1 - nr], intentions, hands[1 - nr], board, trash
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
                    action, knowledge[1 - nr], intentions, hands[1 - nr], board, trash
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
                + " ({:.2f}%): {:.2f}".format(prob * 100, val)
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
