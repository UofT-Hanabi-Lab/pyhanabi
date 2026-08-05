import random
from typing import override, Final

from players import Player
from utils import (
    Action,
    Color,
    Intent,
    COUNTS,
    MAX_HINT_TOKENS,
    get_possible,
    playable,
    discardable,
    potentially_playable,
    potentially_discardable,
    whattodo,
    pretend,
    pretend_discard,
    format_intention,
    format_knowledge,
)

# Penalty used inside the *expected* alignment score when one possible identity
# of A's own card would produce a damaging mismatch for B.
DAMAGING_PENALTY = -100.0

# Tolerance for comparing objective values.
EPSILON = 1e-6


class CaseBasedPlayer(Player):
    """3-player agent that conditions its action on the two preceding turns."""

    def __init__(self, name: str, pnr: int):
        super().__init__(name, pnr)

        # Hint bookkeeping exposed through get_valid_hints/get_redundant_hints,
        # populated by give_intentional_hint (same as SelfIntentionalPlayer).
        self.valid_hints = []
        self.redun_hints = []

        self._next_pnr: Final[int] = (self.pnr + 1) % 3
        """Player ID of the next player in 3P (Player B)."""

        self._sub_pnr: Final[int] = (self.pnr + 2) % 3
        """Player ID of the subsequent player in 3P (Player C)."""

        # Last action taken by each partner since A's own previous turn,
        # keyed by player id. Cleared whenever A itself acts, so at the start
        # of A's turn it holds exactly the two preceding turns:
        #   self._partner_actions.get(B) = B's action two turns ago
        #   self._partner_actions.get(C) = C's action on the previous turn
        self._partner_actions: dict[int, Action] = {}

    @override
    def reset(self) -> None:
        self.valid_hints = []
        self.redun_hints = []
        self._partner_actions = {}

    def get_valid_hints(self):
        return self.valid_hints

    def get_redundant_hints(self):
        return self.redun_hints

    @override
    def inform(self, action: Action, player: int, game) -> None:
        """Record every partner action; clear the buffer on A's own action.

        Unlike SelfIntentionalPlayer.inform, which tracks only the single most
        recent hint aimed at itself, the case-based agent needs the full pair
        of preceding actions (hints to itself AND hints between partners).
        """
        if player == self.pnr:
            # A new A -> B -> C cycle starts after our own action.
            self._partner_actions = {}
        else:
            self._partner_actions[player] = action

    # ------------------------------------------------------------------
    # Small helpers
    # ------------------------------------------------------------------

    def _is_pointed(self, card_knowledge, hint: Action) -> bool:
        """Is a card positively identified by ``hint``?

        The game engine has already applied the hint to the knowledge tables:
        after a color hint, a pointed card has only that color's row nonzero
        while an unpointed card has that row zeroed (symmetrically for ranks).
        So "pointed" reduces to: does any cell consistent with the hint remain?
        (Same convention as SelfIntentionalPlayer.received_hint.)
        """
        if hint.action_type == Action.ActionType.HINT_COLOR:
            return sum(card_knowledge[hint.col]) > 0
        return sum(card_knowledge[c][hint.num - 1] for c in Color) > 0

    def _possibly_expendable(self, possible, trash) -> bool:
        """Does some possible identity have at least one other copy left?

        Used for the U = 1 tier: discarding such a card does not necessarily
        lower the maximum achievable score. Rank 5s are never expendable.
        """
        for col, rank in possible:
            if rank < 5 and COUNTS[rank - 1] - trash.count((col, rank)) >= 2:
                return True
        return False

    def _action_utilities(
        self, hint: Action, nr, knowledge, board, trash, hints
    ) -> dict[tuple[Action.ActionType, int], int]:
        """Compute U(hint, a) for every own play/discard with U > 0.

        Returns a dict mapping (action type, card index) -> utility:
          3 : play a positively identified card that is possibly playable
          2 : discard a positively identified card that is possibly useless
          1 : discard a positively identified card that is possibly expendable
        Discards are only offered when a hint token can be regained (h < 8).
        """
        utilities: dict[tuple[Action.ActionType, int], int] = {}
        for i, k in enumerate(knowledge[nr]):
            if not self._is_pointed(k, hint):
                continue
            possible = get_possible(k)
            if potentially_playable(possible, board):
                utilities[(Action.ActionType.PLAY, i)] = 3
            if hints < MAX_HINT_TOKENS:
                if potentially_discardable(possible, board):
                    utilities[(Action.ActionType.DISCARD, i)] = 2
                elif self._possibly_expendable(possible, trash):
                    utilities[(Action.ActionType.DISCARD, i)] = 1
        return utilities

    # ------------------------------------------------------------------
    # Alignment score S(I_B, A_hat_B) and its post-action expectation
    # ------------------------------------------------------------------

    def _alignment_score(
        self, b_hand, b_knowledge, pending_hint: Action, board, trash
    ) -> float | None:
        """S(I_B, A_hat_B): how well B's predicted response to pending_hint
        matches the goals A computes for B's hand, in the given state.

        Returns the summed score, or None to signal a rejection.
        """
        # I_B = CalculateGoals(B) in the given (possibly simulated) state.
        intents = self._create_intents(b_hand, board, trash)
        total = 0.0
        for intent, k in zip(intents, b_knowledge):
            predicted = whattodo(k, self._is_pointed(k, pending_hint), board)
            if predicted == Action.ActionType.PLAY:
                if intent == Intent.PLAY:
                    total += 3
                else:
                    return None  # damaging: B would misplay this card
            elif predicted == Action.ActionType.DISCARD:
                if intent == Intent.DISCARD:
                    total += 2
                elif intent == Intent.CAN_DISCARD:
                    total += 1
                else:
                    return None  # damaging: B would discard a play/keep card
            # predicted keep contributes 0
        return total

    def _expected_alignment_after(
        self, act: Action, nr, hands, knowledge, board, trash, b_pnr,
        pending_hint: Action,
    ) -> float:
        """Expected S(I_B, A_hat_B) in the state *after* A performs ``act``.

        A cannot see its own card, so the post-action state is uncertain. We
        average S over every identity still possible for the acted-on card,
        weighted by the card counts in A's knowledge table:
          - PLAY of a playable identity  -> that firework advances one rank;
          - PLAY of an unplayable identity (a misplay) -> identity goes to
            the trash, board unchanged (the lost life is not part of S);
          - DISCARD -> identity goes to the trash, board unchanged.
        A damaging-mismatch branch contributes DAMAGING_PENALTY, weighted by
        its probability (see the constant's docstring).
        """
        k = knowledge[nr][act.cnr]
        total_count = sum(sum(row) for row in k)
        if total_count == 0:
            # Degenerate knowledge table; treat as un-evaluable.
            return DAMAGING_PENALTY

        expected = 0.0
        for col in Color:
            for idx, cnt in enumerate(k[col]):
                if cnt == 0:
                    continue
                rank = idx + 1
                prob = cnt / total_count

                # Simulate the post-action board/trash for this identity.
                if (
                    act.action_type == Action.ActionType.PLAY
                    and board[col][1] + 1 == rank
                ):
                    sim_board = list(board)
                    sim_board[col] = (col, rank)  # firework advances
                    sim_trash = trash
                else:
                    # Misplayed or discarded: the card ends up in the trash.
                    sim_board = board
                    sim_trash = trash + [(col, rank)]

                s = self._alignment_score(
                    hands[b_pnr], knowledge[b_pnr], pending_hint,
                    sim_board, sim_trash,
                )
                expected += prob * (DAMAGING_PENALTY if s is None else s)
        return expected

    # ------------------------------------------------------------------
    # Case handlers
    # ------------------------------------------------------------------

    def _act_on_hints(
        self, hint_list, nr, knowledge, board, trash, hints
    ) -> Action | None:
        """Cases 1a, 1c, 2a: pick the own-hand action maximizing summed U.

        hint_list holds one hint (1c, 2a) or two hints (1a); utilities are
        summed across hints, implementing U(a_B, a) + U(a_C, a) for Case 1a.
        Ties break toward higher utility, then PLAY over DISCARD, then the
        lowest card index (consistent with "play the first such card").
        Returns None when no action has positive utility (fall through).
        """
        combined: dict[tuple[Action.ActionType, int], int] = {}
        for hint in hint_list:
            for key, u in self._action_utilities(
                hint, nr, knowledge, board, trash, hints
            ).items():
                combined[key] = combined.get(key, 0) + u

        if not combined:
            return None

        (atype, cnr), best_u = max(
            combined.items(),
            key=lambda kv: (kv[1], kv[0][0] == Action.ActionType.PLAY, -kv[0][1]),
        )
        self.explanation.append(
            [f"Case objective: best U = {best_u} via {atype.display_name} {cnr}"]
        )
        return Action(atype, cnr=cnr)

    def _act_with_observer_term(
        self, own_hint, pending_hint, nr, hands, knowledge, board, trash,
        hints, b_pnr,
    ) -> Action | None:
        """Case 1b: maximize U(a_B, a) + S(I_B, A_hat_B).

        Candidates are the own-hand actions with U > 0 under own_hint
        (B's hint to A); the S term is evaluated in the expected post-action
        state and measures whether the action leaves B able to follow
        ``pending_hint`` (C's hint to B). The status-quo baseline is
        0 + S(current state): "take no U-action and defer to the fallback
        stages". If no candidate beats the baseline, return None.
        """
        baseline = self._alignment_score(
            hands[b_pnr], knowledge[b_pnr], pending_hint, board, trash
        )
        baseline_total = DAMAGING_PENALTY if baseline is None else baseline

        best_action: Action | None = None
        best_total = baseline_total
        utilities = self._action_utilities(
            own_hint, nr, knowledge, board, trash, hints
        )
        for (atype, cnr), u in utilities.items():
            candidate = Action(atype, cnr=cnr)
            s_after = self._expected_alignment_after(
                candidate, nr, hands, knowledge, board, trash, b_pnr,
                pending_hint,
            )
            total = u + s_after
            if total > best_total + EPSILON:
                best_total = total
                best_action = candidate

        if best_action is not None:
            self.explanation.append(
                [f"Case 1b: objective {best_total:.2f} beats baseline "
                 f"{baseline_total:.2f}"]
            )
        return best_action

    def _protect_partner_plan(
        self, pending_hint, nr, hands, knowledge, board, trash, hints, b_pnr,
    ) -> Action | None:
        """Case 2b: maximize S(I_B, A_hat_B) as a pure observer.

        A has no hint of its own, so the only candidates are A's discards
        (which affect S through the trash: expendability and criticality of
        identities in B's hand). Speculative *plays* are deliberately not
        candidates: this agent family never plays a card without hint support,
        and a misplayed life is invisible to S. A candidate must *strictly*
        beat the status-quo S to be chosen; otherwise return None and let the
        fallback stages (intentional hint, etc.) run, which cannot lower S.
        """
        baseline = self._alignment_score(
            hands[b_pnr], knowledge[b_pnr], pending_hint, board, trash
        )
        baseline_total = DAMAGING_PENALTY if baseline is None else baseline

        best_action: Action | None = None
        best_total = baseline_total

        if hints < MAX_HINT_TOKENS:  # discarding is legal
            for cnr in range(len(knowledge[nr])):
                candidate = Action(Action.ActionType.DISCARD, cnr=cnr)
                s_after = self._expected_alignment_after(
                    candidate, nr, hands, knowledge, board, trash, b_pnr,
                    pending_hint,
                )
                if s_after > best_total + EPSILON:
                    best_total = s_after
                    best_action = candidate

        if best_action is not None:
            self.explanation.append(
                [f"Case 2b: discard {best_action.cnr} raises S to "
                 f"{best_total:.2f} from {baseline_total:.2f}"]
            )
        return best_action

    # ------------------------------------------------------------------
    # Helpers copied verbatim from players/self_intentional.py
    # (SelfIntentionalPlayer), so the two agents stay behaviourally
    # identical on the shared stages.
    # ------------------------------------------------------------------

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
                        count += 1
                if count < 2:
                    intentions[i] = Intent.CAN_DISCARD

        return intentions

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

    # ------------------------------------------------------------------
    # Main turn logic
    # ------------------------------------------------------------------

    @override
    def get_action(
        self, nr, hands, knowledge, trash, played, board, valid_actions, hints,
        lives, deck_size,
    ) -> Action:
        # lives and deck_size are part of the repo-wide get_action interface
        # (added for the V4 agent); the case-based algorithm does not use them.
        num_players = len(knowledge)
        assert num_players == 3, "CaseBasedPlayer supports only 3-player games"

        self.explanation = []
        self.valid_hints = []
        self.redun_hints = []
        result: Action | None = None

        b_pnr = self._next_pnr  # B acts immediately after A
        c_pnr = self._sub_pnr   # C acted immediately before A

        a_b = self._partner_actions.get(b_pnr)  # B's action, two turns ago
        a_c = self._partner_actions.get(c_pnr)  # C's action, previous turn

        hint_types = {Action.ActionType.HINT_COLOR, Action.ActionType.HINT_NUMBER}
        b_hinted_a = (
            a_b is not None and a_b.action_type in hint_types and a_b.pnr == self.pnr
        )
        c_hinted_a = (
            a_c is not None and a_c.action_type in hint_types and a_c.pnr == self.pnr
        )
        c_hinted_b = (
            a_c is not None and a_c.action_type in hint_types and a_c.pnr == b_pnr
        )

        # ---- Stage 1: dispatch on the six cases ----
        if not result:
            if b_hinted_a and c_hinted_a:
                # Case 1a: two hints to act on -> maximize U(a_B,a) + U(a_C,a).
                self.explanation.append(["Case 1a"])
                result = self._act_on_hints(
                    [a_b, a_c], nr, knowledge, board, trash, hints
                )
            elif b_hinted_a and c_hinted_b:
                # Case 1b: act on B's hint while protecting C's plan for B ->
                # maximize U(a_B, a) + S(I_B, A_hat_B).
                self.explanation.append(["Case 1b"])
                result = self._act_with_observer_term(
                    a_b, a_c, nr, hands, knowledge, board, trash, hints, b_pnr
                )
            elif b_hinted_a:
                # Case 1c: only B's hint matters -> maximize U(a_B, a).
                # Reduces to the 2-player receiving-hint logic.
                self.explanation.append(["Case 1c"])
                result = self._act_on_hints(
                    [a_b], nr, knowledge, board, trash, hints
                )
            elif c_hinted_a:
                # Case 2a: only C's hint matters -> maximize U(a_C, a).
                self.explanation.append(["Case 2a"])
                result = self._act_on_hints(
                    [a_c], nr, knowledge, board, trash, hints
                )
            elif c_hinted_b:
                # Case 2b: pure observer of C's hint to B ->
                # maximize S(I_B, A_hat_B).
                self.explanation.append(["Case 2b"])
                result = self._protect_partner_plan(
                    a_c, nr, hands, knowledge, board, trash, hints, b_pnr
                )
            else:
                # Case 2c: no actionable hint information remains. Fall through
                # to the naive-extension stages below. Note that the plan's
                # broadened heuristic H(h) = S(I_B,A_hat_B) + S(I_C,A_hat_C)
                # coincides with give_intentional_hint's per-recipient scoring:
                # Predict positively identifies nothing in the non-recipient's
                # hand, so the observer term is always 0.
                self.explanation.append(["Case 2c"])

        # ---- Stage 2: fallback = the baseline stages ----
        # Play a certainly-playable card, or discard a certainly-useless one.
        if not result:
            result = self.play_or_discard(nr, knowledge, board, hints, [], result)

        # Highest-scoring intentional hint over both partners.
        redundant_hints = []
        if not result:
            result, redundant_hints = self.give_intentional_hint(
                nr, hands, knowledge, trash, board, hints, num_players, result
            )

        # At max tokens discarding is illegal: redundant hint, else random.
        if hints == MAX_HINT_TOKENS and not result:
            if redundant_hints:
                result = self.give_redundant_hint(redundant_hints)
            else:
                result = self.give_random_hint(valid_actions)

        # Last resort: discard the card with the lowest expected loss.
        scores = self.discard_card(nr, knowledge, trash, board)

        if result:
            assert result in valid_actions
            return result
        assert scores[0][0] in valid_actions
        return scores[0][0]
