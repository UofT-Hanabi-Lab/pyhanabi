import sys
import hana_sim
from abc import ABCMeta, abstractmethod

from typing import Sequence, override
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

HANASIM_ACTION_TYPE = tuple[int, int, int, int, list[int], int, int]


class AbstractGame(metaclass=ABCMeta):
    players: Sequence[Player]

    @abstractmethod
    def __init__(self, players, log=sys.stdout):
        self.players = players
        self.log = log

    @abstractmethod
    def run(self, turns):
        raise NotImplementedError

    @abstractmethod
    def single_turn(self):
        raise NotImplementedError

    @abstractmethod
    def external_turn(self, action):
        raise NotImplementedError


class HanasimGame(AbstractGame):
    players: Sequence[Player]

    env: hana_sim.HanabiEnv
    knowledge: list[list[list[list[int]]]]

    @override
    def __init__(self, players):
        AbstractGame.__init__(self, players)
        self.env = hana_sim.HanabiEnv(num_players=2)
        self.knowledge = []

    @override
    def run(self, turns):
        # Reset all players and the environment
        obs = self.env.reset()
        for p in self.players:
            p.reset()

        while True:
            # Get action from current player based on game state
            action = self.players[
                obs.current_player_id
            ].get_action(
                obs.current_player_id,
                self._convert_hands(obs.hands),
                self.knowledge,  # TODO: maintain the knowledge attribute during execution
                self._convert_trash(obs.discard),
                self._convert_played(obs.fireworks),
                self._convert_board(obs.fireworks),
                self._convert_valid_actions(obs.legal_actions),
                obs.hints,
            )

            obs = self.env.step(self._convert_action(action))
            if obs.done:
                break

        print("Game done, hits left:", obs.lives_remaining, file=self.log)
        points = self.score(self._convert_board(obs.fireworks))
        print("Points:", points, file=self.log)
        return points

    def _convert_hands(
        self, hands: list[list[tuple[str, int]]]
    ) -> list[list[tuple[Color, int]]]:
        """
        Convert string color representation used in Hanasim hands to Color
        enum used in pyhanabi hands
        """
        # TODO: implement this method

    def _convert_trash(self, discard: list[tuple[str, int]]) -> list[tuple[Color, int]]:
        """
        Convert string color representation used in Hanasim discard to Color
        enum used in pyhanabi trash
        """
        # TODO: implement this method

    def _convert_played(self, fireworks: dict[str, int]) -> list[tuple[Color, int]]:
        """
        Convert string color representation used in Hanasim fireworks to Color
        enum used in pyhanabi played
        """
        # TODO: implement this method

    def _convert_board(self, fireworks: dict[str, int]) -> list[tuple[Color, int]]:
        """
        Convert string color representation used in Hanasim fireworks to Color
        enum used in pyhanabi board
        """
        # TODO: implement this method

    def _convert_valid_actions(
        self, legal_actions: list[HANASIM_ACTION_TYPE]
    ) -> list[Action]:
        """
        Convert legal actions representation used in Hanasim to Action type
        used in pyahanabi
        """
        # TODO: implement this method

    def _convert_action(self, native_action: Action) -> HANASIM_ACTION_TYPE:
        """
        Convert a pyhanabi Action object to HanaSim's action type.
        """
        # TODO: implement this method

    @staticmethod
    def _score(board) -> int:
        return sum(list(map(lambda x: x[1], board)))

    @override
    def single_turn(self):
        pass

    @override
    def external_turn(self, action):
        pass


class Game(AbstractGame):
    players: Sequence[Player]

    @override
    def __init__(self, players, log=sys.stdout, format=0):
        AbstractGame.__init__(self, players)
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
            hands = []
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
            hands = []
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
