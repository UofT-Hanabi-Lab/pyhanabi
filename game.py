import sys
import hana_sim
from abc import ABCMeta, abstractmethod

from typing import Sequence, override, Final
from players import Player
from utils import (
    Action,
    Color,
    make_deck,
    initial_knowledge,
    format_hand,
    COUNTS,
    format_card,
)

MAX_PLAYERS: Final[int] = 5
MIN_PLAYERS: Final[int] = 2

type HanaSimAction = tuple[int, int, int, int, list[int], int, int]
type HanaSimCard = tuple[str, int]
type NativeCard = tuple[Color, int]


COLOR_INT_CONVERSION_DICT = {  # converts Hanasim numbering into pyhanabi numbering
    1: Color.RED,
    2: Color.WHITE,
    3: Color.YELLOW,
    4: Color.GREEN,
    5: Color.BLUE,
    6: None,
}

COLOR_REVERSE_CONVERSION_DICT = {v: k for k, v in COLOR_INT_CONVERSION_DICT.items()}


class AbstractGame(metaclass=ABCMeta):
    players: Sequence[Player]

    @abstractmethod
    def __init__(self, players: Sequence[Player], log=sys.stdout):
        self.players = players
        self.log = log

    @abstractmethod
    def run(self, turns: int) -> int:
        raise NotImplementedError

    @abstractmethod
    def single_turn(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def external_turn(self, action: Action) -> None:
        raise NotImplementedError


class HanasimGame(AbstractGame):
    _env: hana_sim.HanabiEnv
    _obs: hana_sim.Observation
    knowledge: list[list[list[list[int]]]]

    hanasim_colour_map: Final[dict[str, Color]] = {
        "red": Color.RED,
        "white": Color.WHITE,
        "yellow": Color.YELLOW,
        "green": Color.GREEN,
        "blue": Color.BLUE,
    }

    @override
    def __init__(self, players):
        super().__init__(players)
        self._env = hana_sim.HanabiEnv(num_players=2)
        self._reset()

    def _reset(self) -> None:
        self._obs = self._env.reset()
        for p in self.players:
            p.reset()

        hand_size = 4
        if len(self.players) < 4:
            hand_size = 5

        self.knowledge = [
            [initial_knowledge() for __ in range(hand_size)]
            for _ in range(len(self.players))
        ]

    @override
    def run(self, turns=-1):
        if not (MIN_PLAYERS <= len(self.players) <= MAX_PLAYERS):
            raise RuntimeError(
                f"Number of players must be between {MIN_PLAYERS} and {MAX_PLAYERS}"
            )

        self._reset()
        obs = self._obs

        while True:
            # Get action from current player based on game state
            action = self.players[obs.current_player_id].get_action(
                obs.current_player_id,
                self._convert_hands(obs.hands, obs.current_player_id),
                self.knowledge,
                self._convert_trash(obs.discards),
                self._convert_played(obs.fireworks),
                self._convert_board(obs.fireworks),
                HanasimGame._convert_valid_actions(obs.legal_actions),
                obs.hint_tokens,
            )

            acting_player_id: int = obs.current_player_id
            step_result = self._env.step(self._convert_action(action))
            obs = step_result.observation
            self._update_knowledge(
                action,
                acting_player_id,
                self._convert_hands(obs.hands, obs.current_player_id),
            )
            if step_result.done:
                break

        print("Game done, hits left:", obs.lives_remaining, file=self.log)
        points = self._score(self._convert_board(obs.fireworks))
        print("Points:", points, file=self.log)
        return points

    def _update_knowledge(
        self, action: Action, acting_player: int, hands: list[list[NativeCard]]
    ) -> None:
        for p in self.players:
            p.inform(action, acting_player, self)

        if action.action_type == Action.ActionType.HINT_COLOR:
            assert action.col is not None
            assert action.pnr is not None

            # Given a hint for colour X,
            # for every card in the hinted player's hand:
            #     - if the card is positively identified, set all non-X cells in the knowledge to 0
            #     - if the card is negatively identified, set all X cells in the knowledge to 0
            for (col, rank), card_knowledge in zip(
                hands[action.pnr], self.knowledge[action.pnr]
            ):
                if col == action.col:
                    for i in range(len(card_knowledge)):
                        if i != col:
                            card_knowledge[i] = [0 for _ in range(len(card_knowledge))]
                else:
                    for i in range(len(card_knowledge[action.col])):
                        card_knowledge[action.col][i] = 0

        elif action.action_type == Action.ActionType.HINT_NUMBER:
            assert action.num is not None
            assert action.pnr is not None

            # Given a hint for rank N,
            # for every card in the hinted player's hand:
            #     - if the card is positively identified, set all non-N cells in the knowledge to 0
            #     - if the card is negatively identified, set all N cells in the knowledge to 0
            for (col, rank), card_knowledge in zip(
                hands[action.pnr], self.knowledge[action.pnr]
            ):
                if rank == action.num:
                    for k in card_knowledge:
                        for i in range(len(COUNTS)):
                            if i + 1 != rank:
                                k[i] = 0
                else:
                    for k in card_knowledge:
                        k[action.num - 1] = 0

        else:  # the action is either play or discard
            assert action.cnr is not None
            del self.knowledge[acting_player][action.cnr]
            self.knowledge[acting_player].append(initial_knowledge())  # draw a new card

    def _convert_hands(
        self, hands: list[list[HanaSimCard]], curr_player: int
    ) -> list[list[NativeCard]]:
        """
        Convert the representation of the current player's hand info from HanaSim's
        type to pyhanabi's type.

        Precondition:
          - len(self.players) == 2
        """
        partner_pnr: int = (curr_player + 1) % len(self.players)
        visible_hand: list[NativeCard] = [
            self._convert_card(card) for card in hands[partner_pnr]
        ]

        if curr_player == 0:
            return [[], visible_hand]
        else:
            return [visible_hand, []]

    def _convert_card(self, card: HanaSimCard) -> NativeCard:
        return self.hanasim_colour_map[card[0]], card[1] - 1

    def _convert_trash(self, discard: list[HanaSimCard]) -> list[NativeCard]:
        """
        Convert the representation of the discard pile from HanaSim's type to pyhanabi's type.
        """
        return [self._convert_card(card) for card in discard]

    def _convert_played(self, fireworks: dict[str, int]) -> list[NativeCard]:
        """
        Convert the representation of the played cards from HanaSim's type to pyhanabi's type.
        """
        return [
            self._convert_card((color, i))
            for color in fireworks
            for i in range(1, fireworks[color] + 1)
        ]

    def _convert_board(self, fireworks: dict[str, int]) -> list[NativeCard]:
        """
        Convert the representation of the fireworks constructed on the board from
        HanaSim's type to pyhanabi's type.
        """
        # add 1 to cancel out the rank conversion in self._convert_card
        return [self._convert_card((color, fireworks[color] + 1)) for color in fireworks]

    @staticmethod
    def _convert_valid_actions(legal_actions: list[HanaSimAction]) -> list[Action]:
        """
        Convert the representation of legal actions from HanaSim's type to the Action
        type used in pyhanabi.
        """
        actions = []
        for action in legal_actions:
            if action[0] == 1:  # color hint
                move_type = Action.ActionType.HINT_COLOR
            elif action[0] == 2:  # rank hint
                move_type = Action.ActionType.HINT_NUMBER
            elif action[0] == 3:  # play
                move_type = Action.ActionType.PLAY
            elif action[0] == 4:  # discard
                move_type = Action.ActionType.DISCARD
            else:
                continue

            if move_type is Action.ActionType.HINT_COLOR:
                if COLOR_INT_CONVERSION_DICT[action[5]] is not None:
                    actions.append(
                        Action(
                            action_type=move_type,
                            pnr=action[1],
                            col=COLOR_INT_CONVERSION_DICT[action[5]],
                        )
                    )
            elif move_type is Action.ActionType.HINT_NUMBER:
                actions.append(
                    Action(action_type=move_type, pnr=action[1], num=action[6])
                )
            else:
                actions.append(Action(action_type=move_type, cnr=action[3]))
        return actions

    def _convert_action(self, native_action: Action) -> HanaSimAction:
        """
        Convert a pyhanabi Action object to HanaSim's action representation.
        """
        a_type = native_action.action_type
        if a_type is Action.ActionType.HINT_COLOR:
            move_type = 1
        elif a_type is Action.ActionType.HINT_NUMBER:
            move_type = 2
        elif a_type is Action.ActionType.PLAY:
            move_type = 3
        elif a_type is Action.ActionType.DISCARD:
            move_type = 4
        else:
            move_type = 5  # INVALID_MOVE

        # for hints we fill in `to_` & `card_indices`, for non‐hints it's -1 and empty
        color, rank = 6, 6  # 6 represents invalid color and rank
        if move_type == 1:  # color hint
            assert native_action.pnr is not None
            to_ = native_action.pnr
            card_indices = []
            for i, card in enumerate(self._obs.hands[self._obs.current_player_id]):
                card = self._convert_card(card)
                if card[0] == native_action.col:
                    card_indices.append(i)
            card_index = -1
            color = COLOR_REVERSE_CONVERSION_DICT[native_action.col]
        elif move_type == 2:  # rank hint
            assert native_action.num is not None
            assert native_action.pnr is not None
            to_ = native_action.pnr
            card_indices = []
            for i, card in enumerate(self._obs.hands[to_]):
                card = self._convert_card(card)

                # minus 1 because pyhanabi's rank hint action uses 1-based rank
                if card[1] == native_action.num - 1:
                    card_indices.append(i)
            card_index = -1
            rank = native_action.num
        else:  # play or discard
            to_ = -1
            card_indices = []
            card_index = native_action.cnr if native_action.cnr is not None else -1

        # `from_` is the active player issuing this action
        from_ = self._obs.current_player_id

        return move_type, to_, from_, card_index, card_indices, color, rank

    @staticmethod
    def _score(board) -> int:
        return sum(list(map(lambda x: x[1], board)))

    @override
    def single_turn(self):
        """
        Assume the player is a pyhanabi player or a hanasim agent.
        """
        if not self._obs.done():
            action = self.players[self._obs.current_player_id].get_action(
                self._obs.current_player_id,
                self._convert_hands(self._obs.hands, self._obs.current_player_id),
                self.knowledge,
                self._convert_trash(self._obs.discard),
                self._convert_played(self._obs.fireworks),
                self._convert_board(self._obs.fireworks),
                HanasimGame._convert_valid_actions(self._obs.legal_actions),
                self._obs.hint_tokens,
            )
            acting_player_id: int = self._obs.current_player_id
            self._obs = self._env.step(self._convert_action(action))
            self._update_knowledge(
                action,
                acting_player_id,
                self._convert_hands(self._obs.hands, self._obs.current_player_id),
            )

    @override
    def external_turn(self, action: Action):
        """
        Assume the current player is a human player.
        """
        if not self._obs.done():
            acting_player_id: int = self._obs.current_player_id
            self._obs = self._env.step(self._convert_action(action))
            self._update_knowledge(
                action,
                acting_player_id,
                self._convert_hands(self._obs.hands, self._obs.current_player_id),
            )


class Game(AbstractGame):
    @override
    def __init__(self, players, log=sys.stdout, format=0):
        super().__init__(players)
        self.hits = 3
        self.hints = 8
        self.current_player = 0
        self.board = [(c, 0) for c in Color]
        self.played = []
        self.deck = make_deck()
        self.extra_turns = 0
        self.hands = []
        self.knowledge = []
        self.make_hands()
        self.trash = []
        self.log = log
        self.turn = 1
        self.format = format
        self.dopostsurvey = False
        self.study = False
        if self.format:
            print(self.deck, file=self.log)

    def make_hands(self):
        handsize = 4
        if len(self.players) < 4:
            handsize = 5
        for i, p in enumerate(self.players):
            self.hands.append([])
            self.knowledge.append([])
            for j in list(range(handsize)):
                self.draw_card(i)

    def draw_card(self, pnr=None):
        if pnr is None:
            pnr = self.current_player
        if not self.deck:
            return
        self.hands[pnr].append(self.deck[0])
        self.knowledge[pnr].append(initial_knowledge())
        del self.deck[0]

    def perform(self, action: Action):
        for p in self.players:
            p.inform(action, self.current_player, self)
        if self.format:
            print(
                "MOVE:",
                self.current_player,
                action.action_type,
                action.cnr,
                action.pnr,
                action.col,
                action.num,
                file=self.log,
            )
        if action.action_type == Action.ActionType.HINT_COLOR:
            assert action.col is not None
            assert action.pnr is not None

            self.hints -= 1
            print(
                self.players[self.current_player].name,
                "hints",
                self.players[action.pnr].name,
                "about all their",
                action.col.display_name,
                "cards",
                "hints remaining:",
                self.hints,
                file=self.log,
            )
            print(
                self.players[action.pnr].name,
                "has",
                format_hand(self.hands[action.pnr]),
                file=self.log,
            )
            for (col, num), knowledge in zip(
                self.hands[action.pnr], self.knowledge[action.pnr]
            ):
                if col == action.col:
                    for i, k in enumerate(knowledge):
                        if i != col:
                            for i in range(len(k)):
                                k[i] = 0
                else:
                    for i in range(len(knowledge[action.col])):
                        knowledge[action.col][i] = 0
        elif action.action_type == Action.ActionType.HINT_NUMBER:
            assert action.num is not None
            assert action.pnr is not None

            self.hints -= 1
            print(
                self.players[self.current_player].name,
                "hints",
                self.players[action.pnr].name,
                "about all their",
                action.num,
                "hints remaining:",
                self.hints,
                file=self.log,
            )
            print(
                self.players[action.pnr].name,
                "has",
                format_hand(self.hands[action.pnr]),
                file=self.log,
            )
            for (col, num), knowledge in zip(
                self.hands[action.pnr], self.knowledge[action.pnr]
            ):
                if num == action.num:
                    for k in knowledge:
                        for i in range(len(COUNTS)):
                            if i + 1 != num:
                                k[i] = 0
                else:
                    for k in knowledge:
                        k[action.num - 1] = 0
        elif action.action_type == Action.ActionType.PLAY:
            (col, num) = self.hands[self.current_player][action.cnr]
            print(
                self.players[self.current_player].name,
                "plays",
                format_card((col, num)),
                file=self.log,
            )
            if self.board[col][1] == num - 1:
                self.board[col] = (col, num)
                self.played.append((col, num))
                if num == 5:
                    self.hints += 1
                    self.hints = min(self.hints, 8)
                print(
                    "successfully! Board is now", format_hand(self.board), file=self.log
                )
            else:
                self.trash.append((col, num))
                self.hits -= 1
                print("and fails. Board was", format_hand(self.board), file=self.log)
            del self.hands[self.current_player][action.cnr]
            del self.knowledge[self.current_player][action.cnr]
            self.draw_card()
            print(
                self.players[self.current_player].name,
                "now has",
                format_hand(self.hands[self.current_player]),
                file=self.log,
            )
        else:
            self.hints += 1
            self.hints = min(self.hints, 8)
            self.trash.append(self.hands[self.current_player][action.cnr])
            print(
                self.players[self.current_player].name,
                "discards",
                format_card(self.hands[self.current_player][action.cnr]),
                file=self.log,
            )
            print("trash is now", format_hand(self.trash), file=self.log)
            del self.hands[self.current_player][action.cnr]
            del self.knowledge[self.current_player][action.cnr]
            self.draw_card()
            print(
                self.players[self.current_player].name,
                "now has",
                format_hand(self.hands[self.current_player]),
                file=self.log,
            )

    def valid_actions(self):
        valid = []
        for i in range(len(self.hands[self.current_player])):
            valid.append(Action(Action.ActionType.PLAY, cnr=i))
            valid.append(Action(Action.ActionType.DISCARD, cnr=i))
        if self.hints > 0:
            for i, p in enumerate(self.players):
                if i != self.current_player:
                    for col in set(list(map(lambda x: x[0], self.hands[i]))):
                        valid.append(
                            Action(Action.ActionType.HINT_COLOR, pnr=i, col=col)
                        )
                    for num in set(list(map(lambda x: x[1], self.hands[i]))):
                        valid.append(
                            Action(Action.ActionType.HINT_NUMBER, pnr=i, num=num)
                        )
        return valid

    @override
    def run(self, turns=-1):
        for p in self.players:
            p.reset()
        self.turn = 1
        while not self.done() and (turns < 0 or self.turn < turns):
            self.turn += 1
            if not self.deck:
                self.extra_turns += 1
            hands: list[list[NativeCard]] = []
            for i, h in enumerate(self.hands):
                if i == self.current_player:
                    hands.append([])
                else:
                    hands.append(h)
            action = self.players[self.current_player].get_action(
                self.current_player,
                hands,
                self.knowledge,
                self.trash,
                self.played,
                self.board,
                self.valid_actions(),
                self.hints,
            )
            self.perform(action)
            self.current_player += 1
            self.current_player %= len(self.players)
        print("Game done, hits left:", self.hits, file=self.log)
        points = self.score()
        print("Points:", points, file=self.log)
        return points

    def score(self):
        return sum(list(map(lambda x: x[1], self.board)))

    @override
    def single_turn(self):
        if not self.done():
            if not self.deck:
                self.extra_turns += 1
            hands: list[list[NativeCard]] = []
            for i, h in enumerate(self.hands):
                if i == self.current_player:
                    hands.append([])
                else:
                    hands.append(h)
            action = self.players[self.current_player].get_action(
                self.current_player,
                hands,
                self.knowledge,
                self.trash,
                self.played,
                self.board,
                self.valid_actions(),
                self.hints,
            )
            self.perform(action)
            self.current_player += 1
            self.current_player %= len(self.players)

    @override
    def external_turn(self, action):
        if not self.done():
            if not self.deck:
                self.extra_turns += 1
            self.perform(action)
            self.current_player += 1
            self.current_player %= len(self.players)

    def done(self):
        if self.extra_turns == len(self.players) or self.hits == 0:
            return True
        for col, num in self.board:
            if num != 5:
                return False
        return True

    def finish(self):
        if self.format:
            print("Score", self.score(), file=self.log)
            self.log.close()
