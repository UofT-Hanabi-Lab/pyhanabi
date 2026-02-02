from hanabi_live_converter import load_hanabi_live_replay, state_at_turn, get_action_from_state, format_action_display
from players import SelfIntentionalPlayer, Player

replay = load_hanabi_live_replay("json/1721410.txt")
state = state_at_turn(replay, turn_index=9)   # Turn 10

# Same state, different agents
for name, Agent in [("full", SelfIntentionalPlayer), ("random", Player)]:
    agent = Agent("B", 1)
    action = get_action_from_state(agent, state)
    print(f"{name}:", format_action_display(action, state["player_names"]))