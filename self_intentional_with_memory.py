import random

from hanabi import Player, HINT_COLOR, whattodo, HINT_NUMBER, ALL_COLORS, format_intention, DISCARD, PLAY, Action, \
    get_possible, playable, discardable, CANDISCARD, pretend, COLORNAMES, format_knowledge, pretend_discard, f


class SelfIntentionalPlayer(Player):
    def __init__(self, name, pnr):
        super().__init__(name, pnr)
        self.hints = {}
        self.pnr = pnr
        self.gothint = None
        self.last_knowledge = []
        self.last_played = []
        self.last_board = []

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
            if act.type == HINT_COLOR:
                for k in knowledge[nr]:
                    action.append(whattodo(k, sum(k[act.col]) > 0, board))
            elif act.type == HINT_NUMBER:
                for k in knowledge[nr]:
                    cnt = 0
                    for c in ALL_COLORS:
                        cnt += k[c][act.num - 1]
                    action.append(whattodo(k, cnt > 0, board))

        if action:
            self.explanation.append(
                ["What you want me to do"] + list(map(format_intention, action))
            )
            for i, a in enumerate(action):
                if a == PLAY and (not result or result.type == DISCARD):
                    result = Action(PLAY, cnr=i)
                elif a == DISCARD and not result:
                    result = Action(DISCARD, cnr=i)

        self.gothint = None
        for k in knowledge[nr]:
            possible.append(get_possible(k))

        discards = []
        duplicates = []
        for i, p in enumerate(possible):
            if playable(p, board) and not result:
                result = Action(PLAY, cnr=i)
            if discardable(p, board):
                discards.append(i)

        if discards and hints < 8 and not result:
            result = Action(DISCARD, cnr=random.choice(discards))

        playables = []
        useless = []
        discardables = []
        othercards = trash + board
        intentions = [None for i in list(range(handsize))]
        for i, h in enumerate(hands):
            if i != nr:
                for j, (col, n) in enumerate(h):
                    if board[col][1] + 1 == n:
                        playables.append((i, j))
                        intentions[j] = PLAY
                    if board[col][1] >= n:
                        useless.append((i, j))
                        if not intentions[j]:
                            intentions[j] = DISCARD
                    if n < 5 and (col, n) not in othercards:
                        discardables.append((i, j))
                        if not intentions[j]:
                            intentions[j] = CANDISCARD

        self.explanation.append(
            ["Intentions"] + list(map(format_intention, intentions))
        )

        if hints > 0:
            valid = []
            for c in ALL_COLORS:
                action = (HINT_COLOR, c)
                # print("HINT", COLORNAMES[c],)
                (isvalid, score, expl) = pretend(
                    action, knowledge[1 - nr], intentions, hands[1 - nr], board
                )
                self.explanation.append(
                    ["Prediction for: Hint Color " + COLORNAMES[c]]
                    + list(map(format_intention, expl))
                )
                # print(isvalid, score)
                if isvalid:
                    valid.append((action, score))

            for r in range(5):
                r += 1
                action = (HINT_NUMBER, r)
                # print("HINT", r,)

                (isvalid, score, expl) = pretend(
                    action, knowledge[1 - nr], intentions, hands[1 - nr], board
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
                if a[0] == HINT_COLOR:
                    result = Action(HINT_COLOR, pnr=1 - nr, col=a[1])
                else:
                    result = Action(HINT_NUMBER, pnr=1 - nr, num=a[1])

        self.explanation.append(
            ["My Knowledge"] + list(map(format_knowledge, knowledge[nr]))
        )
        possible = [Action(DISCARD, cnr=i) for i in list(range(handsize))]

        scores = list(
            map(lambda p: pretend_discard(p, knowledge[nr], board, trash), possible)
        )

        def format_term(x):
            (col, rank, _, prob, val) = x
            return (
                COLORNAMES[col]
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

    def inform(self, action, player, game):
        if action.type in [PLAY, DISCARD]:
            x = str(action)
            if (action.cnr, player) in self.hints:
                self.hints[(action.cnr, player)] = []
            for i in range(10):
                if (action.cnr + i + 1, player) in self.hints:
                    self.hints[(action.cnr + i, player)] = self.hints[
                        (action.cnr + i + 1, player)
                    ]
                    self.hints[(action.cnr + i + 1, player)] = []
        elif action.pnr == self.pnr:
            self.gothint = (action, player)
            self.last_knowledge = game.knowledge[:]
            self.last_board = game.board[:]
            self.last_trash = game.trash[:]
            self.played = game.played[:]