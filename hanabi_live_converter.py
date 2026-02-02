"""
Convert hanabi.live replay JSON to pyhanabi game state so you can call
player.get_action() at a given turn (e.g. turn 10).

Usage (two steps — convert once, then get actions from different agents):

    1. Convert JSON to state (reusable):
        replay = load_hanabi_live_replay("path/to/1721410.txt")
        state = state_at_turn(replay, turn_index=9)   # 0-based: Turn 10 → turn_index 9

    2. Get action from any agent using that state:
        action1 = get_action_from_state(agent1, state)
        action2 = get_action_from_state(agent2, state)

    Or in one call: action = get_action_at_turn(agent, replay, turn_index=9)

Turn indexing:
    CLI: 1-based (matches hanabi.live). Turn 1 = "A goes first", Turn 2 = before 2nd action, etc.
    Python API (state_at_turn, get_action_at_turn): 0-based turn_index. turn_index=0 → Turn 1, turn_index=9 → Turn 10.

CLI (from project root):
    python -m hanabi_live_converter <replay_path> [turn] -a <agent>
    turn: 1-based turn number (default 10), same as hanabi.live. Turn 1 = before 1st action (A goes first).
    -a/--agent: random, inner, outer, self, intentional, sample, full, timed,
                full-with-mem, full-detect-dead, llm. Default: full.
"""

import json
import copy
from pathlib import Path
from typing import Any

from utils import (
    Action,
    Color,
    MAX_HINT_TOKENS,
    format_card,
    initial_knowledge,
    hint_color,
    hint_rank,
)

# hanabi.live suit index -> pyhanabi Color (hanabi.live: 0=Red, 1=Yellow, 2=Green, 3=Blue, 4=Purple/White)
HANABI_LIVE_SUIT_TO_COLOR: dict[int, Color] = {
    0: Color.RED,
    1: Color.YELLOW,
    2: Color.GREEN,
    3: Color.BLUE,
    4: Color.WHITE,
}

# hanabi.live action types
ACTION_PLAY = 0
ACTION_DISCARD = 1
ACTION_COLOR_HINT = 2
ACTION_RANK_HINT = 3


def format_last_action(replay: dict[str, Any], action_index: int) -> str | None:
    """
    Return a short description of the action at action_index (0-based), or None if no such action.
    The player who took that action is action_index % num_players (since A goes first, then B, then C, ...).
    """
    actions = replay.get("actions", [])
    if action_index < 0 or action_index >= len(actions):
        return None
    names = replay.get("players", [])
    num_players = len(names)
    act = actions[action_index]
    typ = act["type"]
    target = act["target"]
    value = act["value"]
    actor = action_index % num_players
    actor_name = names[actor] if actor < len(names) else f"Player {actor}"

    if typ == ACTION_PLAY:
        return f"player {actor} ({actor_name}) played slot {target}"
    if typ == ACTION_DISCARD:
        return f"player {actor} ({actor_name}) discarded slot {target}"
    if typ == ACTION_COLOR_HINT:
        color = HANABI_LIVE_SUIT_TO_COLOR.get(value, Color.GREEN)
        color_name = color.display_name
        receiver = target
        recv_name = names[receiver] if receiver < len(names) else f"Player {receiver}"
        return f"player {actor} ({actor_name}) told player {receiver} ({recv_name}) about {color_name} cards"
    if typ == ACTION_RANK_HINT:
        receiver = target
        recv_name = names[receiver] if receiver < len(names) else f"Player {receiver}"
        return f"player {actor} ({actor_name}) told player {receiver} ({recv_name}) about {value}s"
    return None


def load_hanabi_live_replay(path: str | Path) -> dict[str, Any]:
    """Load a hanabi.live replay JSON file (e.g. 1721410.txt)."""
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _deck_to_native(replay: dict[str, Any]) -> list[tuple[Color, int]]:
    """Convert hanabi.live deck to list of (Color, rank) with rank 1-5."""
    return [
        (HANABI_LIVE_SUIT_TO_COLOR[c["suitIndex"]], c["rank"])
        for c in replay["deck"]
    ]


def _apply_hint(
    knowledge: list[list[list[list[int]]]],
    hands: list[list[tuple[Color, int]]],
    giver: int,
    receiver: int,
    hint_type: int,
    value: int,
) -> None:
    """Update receiver's knowledge based on hint. Mutates knowledge in place."""
    if hint_type == ACTION_COLOR_HINT:
        color = HANABI_LIVE_SUIT_TO_COLOR[value]
        for slot, card in enumerate(hands[receiver]):
            truth = card[0] == color
            knowledge[receiver][slot] = hint_color(knowledge[receiver][slot], color, truth)
    else:  # ACTION_RANK_HINT
        rank = value  # 1-5
        for slot, card in enumerate(hands[receiver]):
            truth = card[1] == rank
            knowledge[receiver][slot] = hint_rank(knowledge[receiver][slot], rank, truth)


def _build_valid_actions(
    current_player: int,
    hands: list[list[tuple[Color, int]]],
    hints: int,
    num_players: int,
) -> list[Action]:
    """Build list of legal Action objects for the current state (same logic as Game.valid_actions)."""
    valid: list[Action] = []
    hand = hands[current_player]
    for i in range(len(hand)):
        valid.append(Action(Action.ActionType.PLAY, cnr=i))
        valid.append(Action(Action.ActionType.DISCARD, cnr=i))
    if hints > 0:
        for i in range(num_players):
            if i != current_player and hands[i]:
                for col in {c[0] for c in hands[i]}:
                    valid.append(Action(Action.ActionType.HINT_COLOR, pnr=i, col=col))
                for num in {c[1] for c in hands[i]}:
                    valid.append(Action(Action.ActionType.HINT_NUMBER, pnr=i, num=num))
    return valid


def replay_to_turn(
    replay: dict[str, Any],
    turn_index: int,
) -> tuple[
    int,
    list[list[tuple[Color, int]]],
    list[list[list[list[int]]]],
    list[tuple[Color, int]],
    list[tuple[Color, int]],
    list[tuple[Color, int]],
    int,
]:
    """
    Replay the game up to (but not including) the action at turn_index.
    Returns the state *before* the turn_index-th action is taken (so the
    current player is about to act).

    Turn semantics (0-based turn_index; hanabi.live Turn T = turn_index T-1):
        turn_index=0 → Turn 1 (initial state, A goes first). Current player is about to take the 1st action.
        turn_index=1 → Turn 2. Current player is about to take the 2nd action.
        turn_index=N → Turn N+1. Current player is about to take the (N+1)th action.

    Returns:
        current_player,
        hands,
        knowledge,
        trash,
        played,
        board,
        hints,
        remaining_deck (cards not yet drawn, in order)
    """
    deck = _deck_to_native(replay)
    num_players = len(replay["players"])
    hand_size = 5 if num_players < 4 else 4
    actions = replay["actions"]

    # Deal: first N*hand_size cards go to hands. Track deck index per slot for play/discard target.
    deal_size = num_players * hand_size
    hands: list[list[tuple[Color, int]]] = []
    hand_deck_idx: list[list[int]] = []  # hand_deck_idx[p][s] = deck index of card in hands[p][s]
    for p in range(num_players):
        start = p * hand_size
        hand = [deck[i] for i in range(start, start + hand_size)]
        hands.append(hand)
        hand_deck_idx.append(list(range(start, start + hand_size)))
    deck_idx = deal_size

    # Knowledge: one initial_knowledge() per card per player
    knowledge: list[list[list[list[int]]]] = [
        [copy.deepcopy(initial_knowledge()) for _ in range(hand_size)]
        for _ in range(num_players)
    ]

    # Board: (Color, count) per color, count = number of cards on that stack
    board_list: list[tuple[Color, int]] = [(c, 0) for c in Color]
    trash: list[tuple[Color, int]] = []
    played: list[tuple[Color, int]] = []
    hints = MAX_HINT_TOKENS
    strikes = 3

    current_player = 0
    for k in range(min(turn_index, len(actions))):
        act = actions[k]
        typ = act["type"]
        target = act["target"]
        value = act["value"]

        if typ == ACTION_COLOR_HINT or typ == ACTION_RANK_HINT:
            # value: suit index or rank (1-5). target = receiver player index
            receiver = target
            _apply_hint(knowledge, hands, current_player, receiver, typ, value)
            hints -= 1
            current_player = (current_player + 1) % num_players
            continue

        if typ == ACTION_PLAY or typ == ACTION_DISCARD:
            # target = hand slot (0..hand_size-1) OR global deck index (0..49) of the card
            if 0 <= target < len(hands[current_player]):
                slot = target
            else:
                # Global card index: find slot in current player's hand that has this deck index
                try:
                    slot = hand_deck_idx[current_player].index(target)
                except ValueError:
                    slot = 0
            card = hands[current_player][slot]
            col, rank = card

            # Remove card from hand, knowledge, and deck-index tracking
            del hands[current_player][slot]
            del knowledge[current_player][slot]
            del hand_deck_idx[current_player][slot]

            if typ == ACTION_PLAY:
                # board_list is list of (Color, count); we need to update the right stack
                # board_list[i] corresponds to Color(i) or list(Color)[i]
                colors_ordered = list(Color)
                stack_idx = next(i for i, (c, _) in enumerate(board_list) if c == col)
                current_count = board_list[stack_idx][1]
                if current_count + 1 == rank:
                    board_list[stack_idx] = (col, rank)
                    played.append((col, rank))
                    if rank == 5:
                        hints = min(hints + 1, MAX_HINT_TOKENS)
                else:
                    trash.append((col, rank))
                    strikes -= 1
            else:
                trash.append((col, rank))
                hints = min(hints + 1, MAX_HINT_TOKENS)

            # Draw
            if deck_idx < len(deck):
                hands[current_player].append(deck[deck_idx])
                knowledge[current_player].append(copy.deepcopy(initial_knowledge()))
                hand_deck_idx[current_player].append(deck_idx)
                deck_idx += 1

            current_player = (current_player + 1) % num_players

    remaining_deck = deck[deck_idx:]
    return (
        current_player,
        hands,
        knowledge,
        trash,
        played,
        board_list,
        hints,
        remaining_deck,
    )


def state_at_turn(
    replay: dict[str, Any],
    turn_index: int,
) -> dict[str, Any]:
    """
    Convert hanabi.live replay to the state needed for get_action() at the given turn.
    Call this once; pass the returned state to get_action_from_state(player, state)
    for each agent (so different agents can act on the same scenario without re-converting).

    State dict includes: nr, hands, knowledge, trash, played, board, valid_actions, hints,
    plus turn_display, last_action, remaining_deck, player_names, etc.
    """
    (
        current_player,
        hands,
        knowledge,
        trash,
        played,
        board,
        hints,
        remaining_deck,
    ) = replay_to_turn(replay, turn_index)

    # For get_action, the current player doesn't see their own hand
    hands_for_agent = []
    for i, h in enumerate(hands):
        if i == current_player:
            hands_for_agent.append([])
        else:
            hands_for_agent.append(list(h))

    valid_actions = _build_valid_actions(current_player, hands, hints, len(replay["players"]))
    last_action = format_last_action(replay, turn_index - 1) if turn_index >= 1 else None

    return {
        "nr": current_player,
        "hands": hands_for_agent,
        "hands_full": hands,  # full hands (for building valid_actions; agent doesn't get current player's hand)
        "knowledge": knowledge,
        "trash": trash,
        "played": played,
        "board": board,
        "valid_actions": valid_actions,
        "hints": hints,
        "remaining_deck": remaining_deck,
        "turn_index": turn_index,  # 0-based: state *before* the (turn_index+1)th action
        "turn_display": turn_index + 1,  # 1-based, matches hanabi.live (Turn 1, Turn 2, ...)
        "last_action": last_action,  # human-readable description of the previous action, or None at Turn 1
        "num_players": len(replay["players"]),
        "player_names": replay["players"],
    }


def format_action_display(
    action: Action,
    player_names: list[str] | None = None,
) -> str:
    """
    Format an Action for display. If player_names is provided (e.g. from replay["players"]),
    hint targets are shown as "player N (name)" instead of just "N".
    """
    if action.action_type == Action.ActionType.HINT_COLOR and action.col is not None and action.pnr is not None:
        target = f"player {action.pnr}"
        if player_names and 0 <= action.pnr < len(player_names):
            target += f" ({player_names[action.pnr]})"
        return f"hints {target} about all their {action.col.display_name} cards"
    if action.action_type == Action.ActionType.HINT_NUMBER and action.num is not None and action.pnr is not None:
        target = f"player {action.pnr}"
        if player_names and 0 <= action.pnr < len(player_names):
            target += f" ({player_names[action.pnr]})"
        return f"hints {target} about all their {action.num}"
    return str(action)


def print_state_summary(state: dict[str, Any]) -> None:
    """
    Print current turn, deck (remaining), stacks, and each player's hand.
    Uses state["turn_index"]: the turn you provided (state *before* the agent's next action).
    """
    names = state["player_names"]
    turn_display = state.get("turn_display", "?")  # 1-based, matches hanabi.live
    print("\n--- State summary ---")
    print(f"Current turn: {turn_display} (hanabi.live style — state before the agent's next action)")
    last_action = state.get("last_action")
    if last_action is not None:
        print(f"Last action: {last_action}")
    else:
        print("Last action: (none — this is Turn 1, no prior action)")
    print("Remaining deck (undrawn cards, in order):")
    if state["remaining_deck"]:
        print("  " + ", ".join(format_card(c) for c in state["remaining_deck"]))
    else:
        print("  (empty)")
    print("Stacks (color, top rank — largest number played in that color):")
    stacks = [(c, n) for c, n in state["board"] if n > 0]
    if stacks:
        print("  " + ", ".join(format_card((c, n)) for c, n in stacks))
    else:
        print("  (none)")
    print("Players' hands (color, number; left = oldest, right = newest):")
    for i, hand in enumerate(state["hands_full"]):
        name = names[i] if i < len(names) else f"Player {i}"
        print(f"  {name}: " + (", ".join(format_card(c) for c in hand) if hand else "(empty)"))
    print("---\n")


def get_action_from_state(player: Any, state: dict[str, Any]) -> Action:
    """
    Get the action a player would choose given a state from state_at_turn().
    Use this with the same state for different agents to compare decisions.

    Args:
        player: A pyhanabi Player instance (e.g. LLM_Agent) with get_action().
        state: State dict returned by state_at_turn(replay, turn_index).

    Returns:
        The Action the agent chooses.
    """
    return player.get_action(
        state["nr"],
        state["hands"],
        state["knowledge"],
        state["trash"],
        state["played"],
        state["board"],
        state["valid_actions"],
        state["hints"],
    )


def get_action_at_turn(
    player: Any,
    replay: dict[str, Any],
    turn_index: int,
) -> Action:
    """
    Convenience: convert replay to state at turn_index, then return get_action_from_state(player, state).
    """
    state = state_at_turn(replay, turn_index)
    return get_action_from_state(player, state)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Convert a hanabi.live replay to pyhanabi state and get an agent's action at a given turn."
    )
    parser.add_argument(
        "replay_path",
        help="Path to hanabi.live replay JSON (e.g. json/1721410.txt)",
    )
    parser.add_argument(
        "turn",
        type=int,
        nargs="?",
        default=10,
        help="Turn number (1-based, matches hanabi.live). 1=before 1st action (A goes first), 2=before 2nd. Default: 10",
    )
    parser.add_argument(
        "-a",
        "--agent",
        default="full",
        choices=[
            "random",
            "inner",
            "outer",
            "self",
            "intentional",
            "sample",
            "full",
            "timed",
            "full-with-mem",
            "full-detect-dead",
            "llm",
        ],
        help="Agent type to use for get_action. Default: full (SelfIntentionalPlayer)",
    )
    args = parser.parse_args()
    if args.turn < 1:
        parser.error("turn must be >= 1 (hanabi.live uses 1-based turns; Turn 1 = A goes first)")

    replay = load_hanabi_live_replay(args.replay_path)
    # CLI turn is 1-based (hanabi.live); convert to 0-based for internal use
    turn_index = args.turn - 1
    state = state_at_turn(replay, turn_index=turn_index)

    # Print current turn, deck, stacks, and hands (state before the agent acts)
    print_state_summary(state)

    # Build the chosen agent (same types as hanabi.py; import from players to avoid hana_sim)
    from players import (
        Player,
        InnerStatePlayer,
        OuterStatePlayer,
        SelfRecognitionPlayer,
        IntentionalPlayer,
        SamplingRecognitionPlayer,
        SelfIntentionalPlayer,
        TimedPlayer,
        SelfIntentionalPlayerWithMemory,
        SelfIntentionalPlayerDetectDeadColors,
        LLMAgentPlayer,
    )
    player_types = {
        "random": Player,
        "inner": InnerStatePlayer,
        "outer": OuterStatePlayer,
        "self": SelfRecognitionPlayer,
        "intentional": IntentionalPlayer,
        "sample": SamplingRecognitionPlayer,
        "full": SelfIntentionalPlayer,
        "timed": TimedPlayer,
        "full-with-mem": SelfIntentionalPlayerWithMemory,
        "full-detect-dead": SelfIntentionalPlayerDetectDeadColors,
        "llm": LLMAgentPlayer,
    }
    PlayerClass = player_types[args.agent]
    player_name = replay["players"][state["nr"]]
    agent = PlayerClass(player_name, state["nr"])

    print(
        f"Turn {state['turn_display']}: agent (player {state['nr']} ({player_name})) is about to act — "
        f"agent={args.agent}, hints={state['hints']}, valid_actions={len(state['valid_actions'])}"
    )
    action = get_action_from_state(agent, state)
    print("Action:", format_action_display(action, state["player_names"]))
