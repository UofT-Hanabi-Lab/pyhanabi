import random
import os
from typing import override, List, Dict, Any
import json

from openai import OpenAI
from .prompts import general_system_prompt, h_group_prompt, instruction_prompt, shorter_instruction_prompt, shorter_system_prompt

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

class LLMAgentPlayer(Player):
    def __init__(self, name, pnr, use_h_conventions: bool = False, model: str = "deepseek-chat"):
        super().__init__(name, pnr)
        self.client = OpenAI(
            api_key=os.environ.get("OPENAI_API_KEY"),  # Use environment variable
            base_url="https://api.deepseek.com"
        )
        self.model = model
        self.use_h_conventions = use_h_conventions
        self.conversation_history = []
        self.last_justification = None

    @override
    def reset(self) -> None:
        self.last_prompt = None
        self.last_response = None
        self.conversation_history = []

    def _format_actions(self, valid_actions):
        """Turn valid Action objects into a numbered list for the prompt."""
        return "\n".join(
            f"{i}: {str(action)}"
            for i, action in enumerate(valid_actions)
        )
    
    def _summarize_card_knowledge(self, card_knowledge):
        """Summarize a single card slot's knowledge as a list of possible (color, rank)."""
        colors = list(Color)
        ranks = list(range(1, 6))
        possible = []
        for c_idx, row in enumerate(card_knowledge):
            for r_idx, count in enumerate(row):
                if count > 0:
                    possible.append((colors[c_idx], ranks[r_idx]))
        return possible
    
    def log_llm_output(self, player_nr: int, prompt: str, response_text: str, file_path: str = "llm_log.txt"):
        """
        Append LLM input and output to a log file for debugging or analysis.
        """
        with open(file_path, "a", encoding="utf-8") as f:
            f.write(f"\n=== PLAYER {player_nr} TURN ===\n")
            f.write("PROMPT:\n")
            f.write(prompt + "\n\n")
            f.write("LLM RESPONSE:\n")
            f.write(response_text + "\n")
            f.write("="*50 + "\n")

    
    def _list_playable_cards(self, hands, board):
        playable_cards = []
        for pn, hand in enumerate(hands):
            for idx, (col, rank) in enumerate(hand):
                if board[col][1] + 1 == rank:
                    playable_cards.append((pn, idx, col, rank))
        return playable_cards

    def _list_dead_cards(self, hands, board, trash):
        seen = { (c,r) for (c,r) in trash }
        for col, max_rank in board:
            for r in range(1, max_rank+1):
                seen.add((col, r))
        dead = []
        for pn, hand in enumerate(hands):
            for idx, (col,rank) in enumerate(hand):
                if (col,rank) in seen:
                    dead.append((pn, idx, col, rank))
        return dead
    
    def _get_possible_cards_for_slot(self, slot_knowledge):
        """
        Takes the slot knowledge for one card:
            slot_knowledge[color][rank] = remaining count
        Returns a list of all possible (color, rank) pairs that remain possible.
        """
        possible = []

        for color_idx, ranks in enumerate(slot_knowledge):
            for rank_idx, count in enumerate(ranks):
                if count > 0:
                    possible.append((Color(color_idx), rank_idx + 1))  # rank is 1–5

        return possible
    
    def get_possibilities_for_hand(self, player_knowledge):
        """
        Given the player's knowledge for all slots, returns
        a list where each element is the possible cards for that slot.
        """
        return [self._get_possible_cards_for_slot(slot_knowledge)
                for slot_knowledge in player_knowledge]
    
    def get_possibilities_for_hand_clean(self, player_knowledge):
        hand_poss = []

        for slot_knowledge in player_knowledge:
            clean = []
            for color_idx, ranks in enumerate(slot_knowledge):
                for rank_idx, count in enumerate(ranks):
                    if count > 0:
                        clean.append(f"{Color(color_idx).display_name}-{rank_idx+1}")
            hand_poss.append(clean)

        return hand_poss
    
    def summarize_hand_possibilities(self, possibilities):
        """
        possibilities: list[list[(Color, rank)]]
            e.g. the output of get_possibilities_for_hand()

        Returns a single readable string.
        """
        lines = []
        for slot_idx in range(len(possibilities)):
            formatted = ", ".join(possibilities[slot_idx])
            lines.append(f"Slot {slot_idx}: {formatted}")

        return "\n".join(lines)

    
    def _format_player_knowledge(self, knowledge, player_index):
        """Format what a player knows about their own cards."""
        colors = list(Color)
        ranks = list(range(1, 6))
        result = [f"## Player {player_index} Knowledge:"]
        for card_idx, card_knowledge in enumerate(knowledge[player_index]):
            possibilities = self._summarize_card_knowledge(card_knowledge)
            if len(possibilities) == 0:
                result.append(f"- Slot {card_idx}: No information yet")
            elif len(possibilities) <= 3:
                formatted = ", ".join(
                    f"{color.display_name} {rank}" for color, rank in possibilities
                )
                result.append(f"- Slot {card_idx}: Definitely one of [{formatted}]")
            else:
                # Count what we know
                known_colors = set(c for c, r in possibilities)
                known_ranks = set(r for c, r in possibilities)
                if len(known_colors) == 1:
                    result.append(f"- Slot {card_idx}: Color is {list(known_colors)[0].display_name}, rank unknown")
                elif len(known_ranks) == 1:
                    result.append(f"- Slot {card_idx}: Rank is {list(known_ranks)[0]}, color unknown")
                else:
                    result.append(f"- Slot {card_idx}: {len(possibilities)} possibilities remaining")
        return "\n".join(result)
    
    def _format_hand(self, player_nr: int, hands: list[list[tuple[Color, int]]]) -> str:
        """Return a formatted string of a given player's hand."""
        hand = hands[player_nr]
        formatted_cards = []
        for slot, (col, num) in enumerate(hand):
            formatted_cards.append(f"Slot {slot}: {col.display_name} {num}")
        return f"Player {player_nr}'s Hand:\n" + "\n".join(formatted_cards)
    
    def _parse_response(self, player_nr, response_text: str, valid_actions) -> Action:
        """Parse the model's response to extract the action"""
        
        try:


            # Extract JSON from the response
            json_start = response_text.find('{')
            json_end = response_text.rfind('}') + 1
            
            if json_start != -1 and json_end != -1:
                json_str = response_text[json_start:json_end]
                action_data = json.loads(json_str)

                action_type = action_data.get("action")
                slot = action_data.get("slot")
                teammate = action_data.get("teammate")
                color = action_data.get("color")
                number = action_data.get("number")
                self.last_justification = action_data.get("reasoning", "")

                # Convert color string back to Color enum if present
                if color is not None and isinstance(color, str):
                    try:
                        color = Color[color.upper()]
                    except KeyError:
                        print(f"Invalid color: {color}")
                        return random.choice(valid_actions)

                # Validate and create action
                if action_type == "PLAY":
                    if slot is None or slot not in range(5):
                        print(f"Invalid PLAY slot: {slot}")
                        return random.choice(valid_actions)
                    action = Action(Action.ActionType.PLAY, cnr=slot)
                    
                elif action_type == "DISCARD":
                    if slot is None or slot not in range(5):
                        print(f"Invalid DISCARD slot: {slot}")
                        return random.choice(valid_actions)
                    action = Action(Action.ActionType.DISCARD, cnr=slot)
                    
                elif action_type == "HINT_COLOR":
                    if color is None:
                        print("Missing color for HINT_COLOR")
                        return random.choice(valid_actions)
                    valid_teammates = {(player_nr + 1) % 3, (player_nr + 2) % 3}
                    if teammate is None or teammate not in valid_teammates:
                        print(f"Invalid teammate for HINT_COLOR: {teammate}")
                        return random.choice(valid_actions)
                    action = Action(Action.ActionType.HINT_COLOR, pnr=teammate, col=color)
                    
                elif action_type == "HINT_NUMBER":
                    valid_teammates = {(player_nr + 1) % 3, (player_nr + 2) % 3}
                    if teammate is None or teammate not in valid_teammates:
                        print(f"Invalid teammate for HINT_NUMBER: {teammate}")
                        return random.choice(valid_actions)
                    if number is None or number not in range(1, 6):
                        print(f"Invalid number for HINT_NUMBER: {number}")
                        return random.choice(valid_actions)
                    action = Action(Action.ActionType.HINT_NUMBER, pnr=teammate, num=number)
                    
                else:
                    print(f"Unknown action type: {action_type}")
                    return random.choice(valid_actions)
                
                # Verify action is valid
                if action in valid_actions:
                    return action
                else:
                    print(f"Generated action not in valid_actions: {action}")
                    return random.choice(valid_actions)
                
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            print(f"Failed to parse response: {e}")
            print(f"Response was: {response_text[:200]}")
        
        return random.choice(valid_actions)

    def get_action(
        self, nr, hands, knowledge, trash, played, board, valid_actions, hints
    ):
        """Get the next action from the LLM."""

        rules = """
        - The game uses a 50-card deck, divided into five colours (red (R), green (G), blue (B), yellow (Y), white (W)). Each color has cards of ranks 1 to 5. Each color has with three 1's, two 2's, two 3's, two 4's, one 5.
        - Players have to create stacks of each color. Each color stack starts with a Rank 1 card and goes up one by one in ascending order up to Rank 5.  (e.g. Red Stack should go from R1 -> R2 -> R3 -> R4 -> R5). A card can only be played if it is the next in the incremental sequence for its color stack.
        - Players can only see the other's hand, not their own.
        - Players have plausible knowledge of their cards based on previously provided hints by the other player
        - They can either play a card, give a reveal, or discard a card.
        ***Actions:***
                1. Reveal (Clue): Spend a reveal token to reveal cards with a particular color or rank. Revealing a color reveals all cards of that color in partner's hand. Revealing a rank reveals all cards with that rank in partner's hand. The game starts with 8 reveal tokens. If no token left, no more reveals can be given. 
                2. Discard: Discard a card to regain a reveal token and draw a new card. 
                3. Play a Card: If a card played follows sequence in its color stack, it succeeds. Success of rank 5 card in any stack gives an additional reveal token. Failure discards the card, and loses a life. Playing a card you are unsure about is risky as it costs a life and you have only 3 lives. Before playing a card make sure that it's the next card in the sequence for that stack.
        ***The game ends when:***
                - All five stacks are completed. 25 Points. 
                - Three lives have been lost. 0 Points no matter how many cards have been placed in the stack. 
                - After the last card from the deck is drawn and each player has had a final turn. Sum total of the top card ranks of each color stack. 
        """
        
        current_score = sum([col[1] for col in board])
        cards_seen = sum(len(h) for h in hands) + len(trash) + sum(r for _,r in board)
        deck_size = 50 - cards_seen

        trash_str = ", ".join(
            f"{color.display_name} {num}" for color, num in trash
        ) if trash else "None"

        fireworks_str = "\n".join(
            f"  - {color.display_name}: {num}" for color, num in board
        )

        playable_list = self._list_playable_cards(hands, board)
        dead_list = self._list_dead_cards(hands, board, trash)

        playable_str = "\n".join([f"  - Player {pn} Slot {idx}: {c.display_name} {r}" 
                           for pn, idx, c, r in playable_list]) or "None"

        dead_str = "\n".join([f"  - Player {pn} Slot {idx}: {c.display_name} {r}" 
                            for pn, idx, c, r in dead_list]) or "None"

        action_str = self._format_actions(valid_actions)

        # current_player_knowledge = self._format_player_knowledge(knowledge, nr)
        current_player_knowledge_possibilities = self.get_possibilities_for_hand_clean(knowledge[nr])
        current_player_knowledge = self.summarize_hand_possibilities(current_player_knowledge_possibilities)

        teammate_a = (nr + 1) % len(hands)
        teammate_b = (nr + 2) % len(hands)

        teammate_a_hand = self._format_hand(teammate_a, hands)
        # teammate_a_knowledge = self._format_player_knowledge(knowledge, teammate_a)
        teammate_a_knowledge_possibilities = self.get_possibilities_for_hand_clean(knowledge[teammate_a])
        teammate_a_knowledge = self.summarize_hand_possibilities(teammate_a_knowledge_possibilities)
        teammate_b_hand = self._format_hand(teammate_b, hands)
        # teammate_b_knowledge = self._format_player_knowledge(knowledge, teammate_b)
        teammate_b_knowledge_possibilities = self.get_possibilities_for_hand_clean(knowledge[teammate_b])
        teammate_b_knowledge = self.summarize_hand_possibilities(teammate_b_knowledge_possibilities)
        
        # Build enhanced prompt with strategic guidance
        strategic_guidance = """
STRATEGIC PRIORITIES:
1. SAFETY FIRST: Never play a card unless you're certain it's playable
2. INFORMATION: Give hints that provide maximum useful information
3. EFFICIENCY: Only discard when necessary (low on hints) or when certain a card is useless
4. CRITICAL CARDS: Be extremely careful with 5s and unique cards visible in teammates' hands

DECISION FRAMEWORK:
- If you have certain knowledge a card is playable → PLAY it
- If hints available and teammate has playable card → Give helpful HINT
- If hints needed and you're certain a card is useless → DISCARD it
- Otherwise → Give a hint or discard safest card (oldest/leftmost with least info)

RULE: If you choose PLAY or DISCARD, "slot" MUST be one of the valid slots shown.
RULE: If you choose a hint, "teammate" MUST be one of: {teammate_a}, {teammate_b}.
If you choose anything invalid, you lose the game.

SAFE DISCARD HEURISTIC:
- If any of your cards are guaranteed dead → discard the leftmost dead card.
- If none dead: discard your oldest card that is most likely unplayable
  (slot with the largest number of remaining possibilities).
- NEVER discard a 5 unless it is confirmed dead.
"""

        user_prompt = f"""You are Player {nr} in a cooperative Hanabi game.

RULES:
{rules}

GAME STATE:
- Score: {current_score}/25
- Deck Remaining: {deck_size} cards
- Hint Tokens: {hints}/8

{strategic_guidance}

FIREWORKS (Current progress on each color):
{fireworks_str}

DISCARD PILE:
{trash_str}

YOUR KNOWLEDGE (What you know about YOUR cards):
{current_player_knowledge}

VISIBLE PLAYABLE CARDS (guaranteed correct):
{playable_str}

VISIBLE DEAD CARDS (safe discards):
{dead_str}



TEAMMATE {teammate_a}'s VISIBLE HAND (What you can see):
{teammate_a_hand}

Teammate {teammate_a}'s Knowledge (What they know):
{teammate_a_knowledge}

TEAMMATE {teammate_b}'s VISIBLE HAND (What you can see):
{teammate_b_hand}

Teammate {teammate_b}'s Knowledge (What they know):
{teammate_b_knowledge}

Respond with a JSON object:
{{
    "action": "PLAY|DISCARD|HINT_COLOR|HINT_NUMBER",
    "slot": slot_number (0-4, for PLAY/DISCARD only),
    "teammate": player_number (for hints only),
    "color": "red|yellow|green|white|blue" (for HINT_COLOR only),
    "number": 1-5 (for HINT_NUMBER only)
}}

Before producing JSON, write 2–3 bullet points explaining your reasoning.
Then output ONLY the JSON object on a new line.
"""

        if self.use_h_conventions:
            user_prompt = h_group_prompt + "\n\n" + user_prompt

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are an expert Hanabi player. Always respond with valid JSON. Think strategically about card safety and information sharing."},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.3,  # Low but not zero for some variety
                max_tokens=2000,
                response_format={"type": "json_object"}  # Force JSON response
            )

            self.log_llm_output(nr, user_prompt, response.choices[0].message.content)
            
            action = self._parse_response(nr, response.choices[0].message.content, valid_actions)
            return action
            
        except Exception as e:
            print(f"API call failed: {e}")
            return random.choice(valid_actions)
        
    def inform(self, action, player, game):
        """Update the agent based on game events"""
        self.conversation_history.append({
            "player": player,
            "action": str(action),
            "reasoning": self.last_justification
        })