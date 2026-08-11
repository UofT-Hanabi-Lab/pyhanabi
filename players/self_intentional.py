import pdb
import random
from typing import override, Final

from players import Player
from utils import (
    evaluate,
    get_possible,
    highest_playable_cards,
    playable,
    Action,
    discardable,
    Intent,
    Color,
    playable_v2,
    pretend,
    f,
    format_intention,
    format_knowledge,
    pretend_discard,
    pretend_v1,
    pretend_v3,
    whattodo,
    COUNTS,
    MAX_HINT_TOKENS,
)


class SelfIntentionalPlayer(Player):
    def __init__(self, name, pnr, version=0):
        super().__init__(name, pnr)
        self.got_hint = None
        self.hint_was_forced = False
        """V5: True iff the pending hint in got_hint was given while the giver
        held eight hint tokens, so it may have been forced (Section 6.7)."""
        self.valid_hints = []
        self.redun_hints = []
        self.version = version

        self._next_pnr: Final[int] = (self.pnr + 1) % 3
        """Player ID of the next player in 3P"""

        self._sub_pnr: Final[int] = (self.pnr + 2) % 3
        """Player ID of the subsequent player in 3P"""

    @override
    def reset(self) -> None:
        self.got_hint = None
        self.hint_was_forced = False
        self.valid_hints = []
        self.redun_hints = []
    def get_valid_hints(self):
        return self.valid_hints

    def get_redundant_hints(self):
        return self.redun_hints

    def get_action(
        self, nr, hands, knowledge, trash, played, board, valid_actions, hints, lives, deck_size
    ):
        num_players = len(knowledge)
        possible = []
        result = None
        self.explanation = []
        self.explanation.append(["Your Hand:"] + list(map(f, hands[1 - nr])))
        action = []
        self.valid_hints = []
        self.redun_hints = []

        if self.version == 0:
            # Interpret recieved hint
            if self.got_hint:
                result = self.received_hint(nr, knowledge, board, hints, result, action)

            # play or discard
            if not result:
                result = self.play_or_discard(nr, knowledge, board, hints, possible, result)

            # give intentional hint
            if not result:
                result, redundant_hints = self.give_intentional_hint(nr, hands, knowledge, trash, board, hints, num_players, result)

            # give redundant hint
            if hints == MAX_HINT_TOKENS and not result:
                # then I cannot discard

                # first, try to give a redundant hint
                if redundant_hints:
                    result = self.give_redundant_hint(redundant_hints)

                # give random hint
                else:
                    # if there are no redundant hints to give, give a random hint
                    result = self.give_random_hint(valid_actions)

            # discard
            scores = self.discard_card(nr, knowledge, trash, board)

        if self.version == 1:
            # Interpret recieved hint
            if self.got_hint:
                result = self.received_hint(nr, knowledge, board, hints, result, action)

            # play or discard
            if not result:
                result = self.play_or_discard(nr, knowledge, board, hints, possible, result)

            # give intentional hint
            if not result:
                result, redundant_hints = self.give_intentional_hint(nr, hands, knowledge, trash, board, hints, num_players, result)

            # give redundant hint
            if hints == MAX_HINT_TOKENS and not result:
                # then I cannot discard

                # first, try to give a redundant hint
                # result = self.give_hint_v1(nr, hands, knowledge, trash, board, hints, num_players, result)
                if redundant_hints and not result:
                    result = self.give_redundant_hint(redundant_hints)

                result = self.give_hint_v1(nr, hands, knowledge, trash, board, hints, num_players, result)

                # give random hint
                if not result:
                    # if there are no redundant hints to give, give a random hint
                    result = self.give_random_hint(valid_actions)

            # discard
            scores = self.discard_card(nr, knowledge, trash, board)

        if self.version == 2:
            # play a certainly playable card, or discard a certainly useless one
            result = self.play_or_discard(nr, knowledge, board, hints, possible, result)

            # interpret received hint only if no safe action was found
            if self.got_hint:
                if not result:
                    result = self.received_hint(nr, knowledge, board, hints, result, action)
                else:
                    self.got_hint = None

            # give intentional hint
            if not result:
                result, redundant_hints = self.give_intentional_hint(nr, hands, knowledge, trash, board, hints, num_players, result)

            # At max tokens cannot discard: redundant hint, else random hint
            if hints == MAX_HINT_TOKENS and not result:
                if redundant_hints:
                    result = self.give_redundant_hint(redundant_hints)
                else:
                    result = self.give_random_hint(valid_actions)

            # Fallback: discard the card with the lowest expected loss
            scores = self.discard_card(nr, knowledge, trash, board)

        if self.version == 3:
            # Interpret recieved hint
            if self.got_hint:
                result = self.received_hint(nr, knowledge, board, hints, result, action)

            # play or discard
            if not result:
                result = self.play_or_discard(nr, knowledge, board, hints, possible, result)

            # give intentional hint
            if not result:
                result, redundant_hints = self.give_intentional_hint(nr, hands, knowledge, trash, board, hints, num_players, result)

            # give redundant hint
            if hints == MAX_HINT_TOKENS and not result:
                # then I cannot discard
                result = self.give_hint_v3(nr, hands, knowledge, trash, board, hints, num_players, result)
                # first, try to give a redundant hint
                if redundant_hints and not result:
                    result = self.give_redundant_hint(redundant_hints)

                # result = self.give_hint_v3(nr, hands, knowledge, trash, board, hints, num_players, result)

                # give random hint
                if not result:
                    # if there are no redundant hints to give, give a random hint
                    result = self.give_random_hint(valid_actions)

            # discard
            scores = self.discard_card(nr, knowledge, trash, board)


        if self.version == 4:
            # Interpret recieved hint
            if self.got_hint:
                result = self.received_hint(nr, knowledge, board, hints, result, action)

            # play or discard
            if not result:
                result = self.play_or_discard(nr, knowledge, board, hints, possible, result)


            # give intentional hint
            if not result:
                result, redundant_hints = self.give_intentional_hint(nr, hands, knowledge, trash, board, hints, num_players, result)

            # added this
            if deck_size < 16 and not result:
                result = self.play_v2(nr, knowledge, board, hints, possible, result, deck_size, lives)

            # added this
            if deck_size < 20 and not result:
                result = self.give_hint_v3(nr, hands, knowledge, trash, board, hints, num_players, result)
                if not result and hints > 0:
                    result = self.give_best_hint(nr, hands, knowledge, trash, board, hints, num_players, result)

            # give redundant hint
            if hints == MAX_HINT_TOKENS and not result:
                # then I cannot discard
                #include reduncant hints in this algo
                result = self.give_hint_v3(nr, hands, knowledge, trash, board, hints, num_players, result)
                # first, try to give a redundant hint
                #if redundant_hints and not result:
                 #   result = self.give_redundant_hint(redundant_hints)

                # result = self.give_hint_v3(nr, hands, knowledge, trash, board, hints, num_players, result)

                # give random hint
                if not result:
                    # if there are no redundant hints to give, give a random hint
                    result = self.give_random_hint(valid_actions)

            # discard
            scores = self.discard_card(nr, knowledge, trash, board)

        if self.version == 5:
            # Interpret recieved hint, unless it may have been forced
            if self.got_hint:
                if self.hint_was_forced:
                    self.explanation.append(
                        ["Received hint may have been forced (giver held 8 "
                         "tokens): mental state updated, intention not interpreted"]
                    )
                    self.got_hint = None
                    self.hint_was_forced = False
                else:
                    result = self.received_hint(nr, knowledge, board, hints, result, action)
                    self.hint_was_forced = False

            # play or discard
            if not result:
                result = self.play_or_discard(nr, knowledge, board, hints, possible, result)

            # give intentional hint
            if not result:
                result, redundant_hints = self.give_intentional_hint(nr, hands, knowledge, trash, board, hints, num_players, result)

            # forced to hint: give the informational rank hint of Section 6.7
            if hints == MAX_HINT_TOKENS and not result:
                # then I cannot discard
                result = self.give_forced_rank_hint(nr, hands, knowledge, board, num_players)
                if not result:
                    result = self.give_random_hint(valid_actions)

            # discard
            scores = self.discard_card(nr, knowledge, trash, board)

        if result:
            assert result in valid_actions
            return result
        assert scores[0][0] in valid_actions
        return scores[0][0]

    def give_redundant_hint(self, redundant_hints):
        selected_action, hintee_id = random.choice(redundant_hints)
        if selected_action[0] is Action.ActionType.HINT_COLOR:
            result = Action(
                            Action.ActionType.HINT_COLOR,
                            pnr=hintee_id,
                            col=Color(selected_action[1]),
                        )
        else:
            result = Action(
                            Action.ActionType.HINT_NUMBER,
                            pnr=hintee_id,
                            num=selected_action[1],
                        )
        return result

    def discard_card(self, nr, knowledge, trash, board):
        self.explanation.append(
            ["My Knowledge"] + list(map(format_knowledge, knowledge[nr]))
        )
        possible = [
            Action(Action.ActionType.DISCARD, cnr=i) for i in range(self._hand_size)
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
        return scores

    def give_random_hint(self, valid_actions):
        result = random.choice(
                    [
                        action
                        for action in valid_actions
                        if action.action_type
                        in {Action.ActionType.HINT_COLOR, Action.ActionType.HINT_NUMBER}
                    ]
                )

        return result

    def give_forced_rank_hint(self, nr, hands, knowledge, board, num_players):
        """V5: choose the forced rank hint of Section 6.7.

        Among every legal rank hint (one per rank present in each partner's
        hand), prefer a rank that no firework is currently awaiting, so that
        the hint does not suggest a play. Among the preferred hints, give the
        one that removes the most identities from the recipient's mental
        state; if every rank in every hand is awaited by some firework, give
        whichever rank hint removes the most identities.

        Returns the chosen hint as an Action, or None if no partner holds any
        card (which cannot happen in a running game).
        """
        # the rank each unfinished firework is awaiting: one above its top
        awaited_ranks = {board[c][1] + 1 for c in Color if board[c][1] < 5}

        # candidate tuples: (preferred, identities removed, hintee, rank)
        candidates: list[tuple[bool, int, int, int]] = []

        for hintee_id in range(num_players):
            if hintee_id == nr:
                continue

            # a rank hint is only legal for ranks the hintee actually holds
            for r in sorted({num for (_, num) in hands[hintee_id]}):
                removed = self._identities_removed_by_rank_hint(
                    hands[hintee_id], knowledge[hintee_id], r
                )
                preferred = r not in awaited_ranks
                candidates.append((preferred, removed, hintee_id, r))
                self.explanation.append(
                    [
                        "Forced rank hint candidate",
                        "Rank " + str(r) + " to player " + str(hintee_id),
                        "not awaited" if preferred else "awaited by a firework",
                        "removes " + str(removed) + " identities",
                    ]
                )

        if not candidates:
            return None

        # Sorting on (preferred, removed) descending implements the two-level
        # preference: any non-awaited rank beats any awaited one, and ties
        # are broken by the number of identities removed. The sort is stable,
        # so remaining ties keep hand order (next player first, lowest rank
        # first), which keeps the choice deterministic.
        candidates.sort(key=lambda x: (x[0], x[1]), reverse=True)
        _, _, hintee_id, rank = candidates[0]

        return Action(Action.ActionType.HINT_NUMBER, pnr=hintee_id, num=rank)

    def _identities_removed_by_rank_hint(self, hand, hand_knowledge, rank):
        """V5: count the identities a rank hint removes from a hand's mental
        state.

        The count covers every card in the hand, not only the cards the hint
        positively identifies: for an identified card (its true rank equals
        rank) every still-possible identity of a *different* rank is removed,
        while for every other card the identities of rank rank are removed.
        An identity counts as removed when its cell goes from a positive
        count to zero.
        """
        removed = 0
        for (_, num), k in zip(hand, hand_knowledge):
            if num == rank:
                # positively identified: all other ranks are ruled out
                for c in Color:
                    for i in range(len(COUNTS)):
                        if i + 1 != rank and k[c][i] > 0:
                            removed += 1
            else:
                # not identified: the hinted rank is ruled out for this card
                for c in Color:
                    if k[c][rank - 1] > 0:
                        removed += 1
        return removed

    def _giver_hint_tokens(self, game):
        """V5: return the number of hint tokens the giver held *when giving*
        the hint that inform() is currently processing.

        The two engines expose this differently:
        - HanasimGame calls inform() after advancing its observation, so
          game._obs.hint_tokens is the post-hint count and the hint has
          already spent one token: add it back.
        - The legacy Game calls inform() before deducting the token, so
          game.hints is already the pre-hint count.
        """
        obs = getattr(game, "_obs", None)
        if obs is not None:
            return min(obs.hint_tokens + 1, MAX_HINT_TOKENS)
        return game.hints

    def give_best_hint(self, nr, hands, knowledge, trash, board, hints, num_players, result):
        if num_players == 2:
            intents_for_next = self._create_intents(
                hands[(self.pnr + 1) % 2], board, trash
            )
            self.explanation.append(
                ["Intentions for next player"]
                + list(map(format_intention, intents_for_next))
            )
            intents_for_sub = None
        else:
            intents_for_next = self._create_intents(hands[self._next_pnr], board, trash)
            self.explanation.append(
                ["Intentions for next player"]
                + list(map(format_intention, intents_for_next))
            )

            intents_for_sub = self._create_intents(hands[self._sub_pnr], board, trash)
            self.explanation.append(
                ["Intentions for subsequent player"]
                + list(map(format_intention, intents_for_sub))
            )

        if hints > 0:
            hint_action: tuple[Action.ActionType, Color | int]
            valid: list[tuple[tuple[Action.ActionType, Color | int], int, int]] = []
            redundant_hints: list[
                tuple[tuple[Action.ActionType, Color | int], int]
            ] = []

            for hintee_id in range(num_players):
                if hintee_id == nr:
                    continue
                elif num_players == 2 or hintee_id == self._next_pnr:
                    hintee_intentions = intents_for_next
                else:
                    assert intents_for_sub is not None
                    hintee_intentions = intents_for_sub

                for c in Color:
                    hint_action = (Action.ActionType.HINT_COLOR, c)
                    isvalid, score, expl = evaluate(
                        hint_action,
                        knowledge[hintee_id],
                        hintee_intentions,
                        hands[hintee_id],
                        board,
                        trash,
                    )
                    self.explanation.append(
                        ["Prediction for: Hint Color " + c.display_name]
                        + list(map(format_intention, expl))
                    )
                    if isvalid:
                        valid.append((hint_action, score, hintee_id))


                for r in range(5):
                    r += 1
                    hint_action = (Action.ActionType.HINT_NUMBER, r)
                    isvalid, score, expl = evaluate(
                        hint_action,
                        knowledge[hintee_id],
                        hintee_intentions,
                        hands[hintee_id],
                        board,
                        trash,
                    )
                    self.explanation.append(
                        ["Prediction for: Hint Number " + str(r)]
                        + list(map(format_intention, expl))
                    )
                    if isvalid:
                        valid.append((hint_action, score, hintee_id))

            if valid and not result:
                # sort descending by hint score
                valid.sort(key=lambda x: x[1], reverse=True)

                selected_action, _, hintee_id = valid[0]
                if selected_action[0] is Action.ActionType.HINT_COLOR:
                    result = Action(
                        Action.ActionType.HINT_COLOR,
                        pnr=hintee_id,
                        col=Color(selected_action[1]),
                    )
                else:
                    result = Action(
                        Action.ActionType.HINT_NUMBER,
                        pnr=hintee_id,
                        num=selected_action[1],
                    )

        return result

    def give_intentional_hint(self, nr, hands, knowledge, trash, board, hints, num_players, result):
        redundant_hints = []
        if num_players == 2:
            intents_for_next = self._create_intents(
                hands[(self.pnr + 1) % 2], board, trash
            )
            self.explanation.append(
                ["Intentions for next player"]
                + list(map(format_intention, intents_for_next))
            )
            intents_for_sub = None
        else:
            intents_for_next = self._create_intents(hands[self._next_pnr], board, trash)
            self.explanation.append(
                ["Intentions for next player"]
                + list(map(format_intention, intents_for_next))
            )

            intents_for_sub = self._create_intents(hands[self._sub_pnr], board, trash)
            self.explanation.append(
                ["Intentions for subsequent player"]
                + list(map(format_intention, intents_for_sub))
            )

        if hints > 0:
            hint_action: tuple[Action.ActionType, Color | int]
            valid: list[tuple[tuple[Action.ActionType, Color | int], int, int]] = []
            redundant_hints: list[
                tuple[tuple[Action.ActionType, Color | int], int]
            ] = []

            for hintee_id in range(num_players):
                if hintee_id == nr:
                    continue
                elif num_players == 2 or hintee_id == self._next_pnr:
                    hintee_intentions = intents_for_next
                else:
                    assert intents_for_sub is not None
                    hintee_intentions = intents_for_sub

                for c in Color:
                    hint_action = (Action.ActionType.HINT_COLOR, c)
                    (isvalid, score, expl) = pretend(
                        hint_action,
                        knowledge[hintee_id],
                        hintee_intentions,
                        hands[hintee_id],
                        board,
                        trash
                    )
                    self.explanation.append(
                        ["Prediction for: Hint Color " + c.display_name]
                        + list(map(format_intention, expl))
                    )
                    if isvalid:
                        valid.append((hint_action, score, hintee_id))
                        if hint_action[0] == Action.ActionType.HINT_NUMBER:
                            self.valid_hints.append((hint_action[1], hintee_id, score))
                        else:
                            self.valid_hints.append((hint_action[1].display_name, hintee_id, score))
                    if expl == ["No new information"]:
                        redundant_hints.append((hint_action, hintee_id))
                        if hint_action[0] == Action.ActionType.HINT_NUMBER:
                            self.redun_hints.append((hint_action[1], hintee_id, score))
                        else:
                            self.redun_hints.append((hint_action[1].display_name, hintee_id, score))

                for r in range(5):
                    r += 1
                    hint_action = (Action.ActionType.HINT_NUMBER, r)
                    (isvalid, score, expl) = pretend(
                        hint_action,
                        knowledge[hintee_id],
                        hintee_intentions,
                        hands[hintee_id],
                        board,
                        trash
                    )
                    self.explanation.append(
                        ["Prediction for: Hint Rank " + str(r)]
                        + list(map(format_intention, expl))
                    )
                    if isvalid:
                        valid.append((hint_action, score, hintee_id))
                        if hint_action[0] == Action.ActionType.HINT_NUMBER:
                            self.valid_hints.append((hint_action[1], hintee_id, score))
                        else:
                            self.valid_hints.append((hint_action[1].display_name, hintee_id, score))
                    if expl == ["No new information"]:
                        redundant_hints.append((hint_action, hintee_id))
                        if hint_action[0] == Action.ActionType.HINT_NUMBER:
                            self.redun_hints.append((hint_action[1], hintee_id, score))
                        else:
                            self.redun_hints.append((hint_action[1].display_name, hintee_id, score))


            if valid and not result:
                # sort descending by hint score
                valid.sort(key=lambda x: x[1], reverse=True)

                selected_action, _, hintee_id = valid[0]
                if selected_action[0] is Action.ActionType.HINT_COLOR:
                    result = Action(
                        Action.ActionType.HINT_COLOR,
                        pnr=hintee_id,
                        col=Color(selected_action[1]),
                    )
                else:
                    result = Action(
                        Action.ActionType.HINT_NUMBER,
                        pnr=hintee_id,
                        num=selected_action[1],
                    )

        return result, redundant_hints

    def give_hint_v1(self, nr, hands, knowledge, trash, board, hints, num_players, result):
        if num_players == 2:
            intents_for_next = self._create_intents(
                hands[(self.pnr + 1) % 2], board, trash
            )
            self.explanation.append(
                ["Intentions for next player"]
                + list(map(format_intention, intents_for_next))
            )
            intents_for_sub = None
        else:
            intents_for_next = self._create_intents(hands[self._next_pnr], board, trash)
            self.explanation.append(
                ["Intentions for next player"]
                + list(map(format_intention, intents_for_next))
            )

            intents_for_sub = self._create_intents(hands[self._sub_pnr], board, trash)
            self.explanation.append(
                ["Intentions for subsequent player"]
                + list(map(format_intention, intents_for_sub))
            )

        if hints > 0:
            hint_action: tuple[Action.ActionType, Color | int]
            valid: list[tuple[tuple[Action.ActionType, Color | int], int, int]] = []
            redundant_hints: list[
                tuple[tuple[Action.ActionType, Color | int], int]
            ] = []

            for hintee_id in range(num_players):
                if hintee_id == nr:
                    continue
                elif num_players == 2 or hintee_id == self._next_pnr:
                    hintee_intentions = intents_for_next
                else:
                    assert intents_for_sub is not None
                    hintee_intentions = intents_for_sub

                for c in Color:
                    hint_action = (Action.ActionType.HINT_COLOR, c)
                    (isvalid, score, expl) = pretend_v1(
                        hint_action,
                        knowledge[hintee_id],
                        hintee_intentions,
                        hands[hintee_id],
                        board,
                        trash,
                    )
                    self.explanation.append(
                        ["Prediction for: Hint Color " + c.display_name]
                        + list(map(format_intention, expl))
                    )
                    if isvalid:
                        valid.append((hint_action, score, hintee_id))

                for r in range(5):
                    r += 1
                    hint_action = (Action.ActionType.HINT_NUMBER, r)
                    (isvalid, score, expl) = pretend_v1(
                        hint_action,
                        knowledge[hintee_id],
                        hintee_intentions,
                        hands[hintee_id],
                        board,
                        trash,
                    )
                    self.explanation.append(
                        ["Prediction for: Hint Rank " + str(r)]
                        + list(map(format_intention, expl))
                    )
                    if isvalid:
                        valid.append((hint_action, score, hintee_id))

            if valid and not result:
                # sort descending by hint score
                valid.sort(key=lambda x: x[1], reverse=True)

                selected_action, _, hintee_id = valid[0]
                if selected_action[0] is Action.ActionType.HINT_COLOR:
                    result = Action(
                        Action.ActionType.HINT_COLOR,
                        pnr=hintee_id,
                        col=Color(selected_action[1]),
                    )
                else:
                    result = Action(
                        Action.ActionType.HINT_NUMBER,
                        pnr=hintee_id,
                        num=selected_action[1],
                    )

        return result

    def give_hint_v3(self, nr, hands, knowledge, trash, board, hints, num_players, result):
        if num_players == 2:
            intents_for_next = self._create_intents(
                hands[(self.pnr + 1) % 2], board, trash
            )
            self.explanation.append(
                ["Intentions for next player"]
                + list(map(format_intention, intents_for_next))
            )
            intents_for_sub = None
        else:
            intents_for_next = self._create_intents(hands[self._next_pnr], board, trash)
            self.explanation.append(
                ["Intentions for next player"]
                + list(map(format_intention, intents_for_next))
            )

            intents_for_sub = self._create_intents(hands[self._sub_pnr], board, trash)
            self.explanation.append(
                ["Intentions for subsequent player"]
                + list(map(format_intention, intents_for_sub))
            )

        if hints > 0:
            hint_action: tuple[Action.ActionType, Color | int]
            valid: list[tuple[tuple[Action.ActionType, Color | int], int, int]] = []
            redundant_hints: list[
                tuple[tuple[Action.ActionType, Color | int], int]
            ] = []

            for hintee_id in range(num_players):
                if hintee_id == nr:
                    continue
                elif num_players == 2 or hintee_id == self._next_pnr:
                    hintee_intentions = intents_for_next
                else:
                    assert intents_for_sub is not None
                    hintee_intentions = intents_for_sub

                for c in Color:
                    hint_action = (Action.ActionType.HINT_COLOR, c)
                    (isvalid, score, expl) = pretend_v3(
                        hint_action,
                        knowledge[hintee_id],
                        hintee_intentions,
                        hands[hintee_id],
                        board,
                        trash
                    )
                    self.explanation.append(
                        ["Prediction for: Hint Color " + c.display_name]
                        + list(map(format_intention, expl))
                    )
                    if isvalid:
                        valid.append((hint_action, score, hintee_id))

                for r in range(5):
                    r += 1
                    hint_action = (Action.ActionType.HINT_NUMBER, r)
                    (isvalid, score, expl) = pretend_v3(
                        hint_action,
                        knowledge[hintee_id],
                        hintee_intentions,
                        hands[hintee_id],
                        board,
                        trash
                    )
                    self.explanation.append(
                        ["Prediction for: Hint Rank " + str(r)]
                        + list(map(format_intention, expl))
                    )
                    if isvalid:
                        valid.append((hint_action, score, hintee_id))

            if valid and not result:
                # sort descending by hint score
                valid.sort(key=lambda x: x[1], reverse=True)

                selected_action, _, hintee_id = valid[0]
                if selected_action[0] is Action.ActionType.HINT_COLOR:
                    result = Action(
                        Action.ActionType.HINT_COLOR,
                        pnr=hintee_id,
                        col=Color(selected_action[1]),
                    )
                else:
                    result = Action(
                        Action.ActionType.HINT_NUMBER,
                        pnr=hintee_id,
                        num=selected_action[1],
                    )

        return result

    def play_or_discard(self, nr, knowledge, board, hints, possible, result):
        for k in knowledge[nr]:
            possible.append(get_possible(k))

        discardable_idx = []
        for i, p in enumerate(possible):
            if playable(p, board) and not result:
                result = Action(Action.ActionType.PLAY, cnr=i)
            if discardable(p, board):
                discardable_idx.append(i)

        if discardable_idx and hints < MAX_HINT_TOKENS and not result:
            result = Action(
                Action.ActionType.DISCARD, cnr=random.choice(discardable_idx)
            )

        return result

    def play_v2(self, nr, knowledge, board, hints, possible, result, deck_size, lives):
        for i, k in enumerate(knowledge[nr]):
            if playable_v2(k, board, deck_size, lives) and not result:
                result = Action(Action.ActionType.PLAY, cnr=i)
        return result

    def received_hint(self, nr, knowledge, board, hints, result, action):
        (act, plr) = self.got_hint
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
                elif a == Action.ActionType.DISCARD and not result and hints < MAX_HINT_TOKENS:
                    result = Action(Action.ActionType.DISCARD, cnr=i)

        self.got_hint = None
        return result

    def _create_intents(
        self,
        hand: list[tuple[Color, int]],
        board: list[tuple[Color, int]],
        trash: list[tuple[Color, int]],
    ) -> list[Intent | None]:
        intentions: list[Intent | None] = [None for _ in range(len(hand))]

        for i, (col, n) in enumerate(hand):
            if board[col][1] + 1 == n:
                intentions[i] = Intent.PLAY
            elif board[col][1] >= n:
                intentions[i] = Intent.DISCARD
            elif n < 5 and n > 1 and (col, n) not in (trash + board):
                # DONE: this condition doesn't account for there being three 1s of each colour
                intentions[i] = Intent.CAN_DISCARD
            elif n == 1:
                count = 0
                for c in (trash + board):
                    if col == c[0] and n == c[1]:
                        count+=1
                if count < 2:
                    intentions[i] = Intent.CAN_DISCARD

        return intentions

    def inform(self, action, player, game):
        if action.pnr == self.pnr and action.action_type in {
            Action.ActionType.HINT_COLOR,
            Action.ActionType.HINT_NUMBER,
        }:
            self.got_hint = (action, player)
            # V5: record whether the giver held eight tokens when giving this
            # hint (making it potentially forced). Versions 0-4 never read
            # this flag, so setting it unconditionally is harmless.
            self.hint_was_forced = (
                self._giver_hint_tokens(game) == MAX_HINT_TOKENS
            )
