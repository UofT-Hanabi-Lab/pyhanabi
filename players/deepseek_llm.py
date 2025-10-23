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
    def __init__(self, name, pnr, use_h_conventions: bool = False, model: str = "deepseek-reasoner"):
        super().__init__(name, pnr)
        self.client = OpenAI(
            api_key="API_KEY",
            base_url="https://api.deepseek.com/v1",
        )
        self.use_h_conventions = use_h_conventions
        self.conversation_history = []
        self.last_justification = None

    @override
    def reset(self) -> None:
        self.last_prompt = None
        self.last_response = None

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
    
    def _format_player_knowledge(self, knowledge, player_index):
        colors = list(Color)
        ranks = list(range(1, 6))
        result = [f"## Player {player_index} Knowledge:"]
        for card_idx, card_knowledge in enumerate(knowledge[player_index]):
            possibilities = self._summarize_card_knowledge(card_knowledge)
            formatted = ", ".join(
                f"{color.display_name} {rank}" for color, rank in possibilities
            )
            result.append(f"- Card {card_idx}: could be [{formatted}]")
        return "\n".join(result)
    
    def _format_hand(self, player_nr: int, hands: list[list[tuple[Color, int]]]) -> str:
        """
        Return a formatted string of a given player's hand.
        """
        hand = hands[player_nr]
        formatted_cards = []
        for slot, (col, num) in enumerate(hand):
            formatted_cards.append(f"Slot {slot}: {col.display_name} {num}")
        return f"Player {player_nr}'s Hand:\n" + "\n".join(formatted_cards)
    
    def _parse_response(self, player_nr, response_text: str, valid_actions) -> Action:
        """Parse the model's response to extract the action"""
        
        # Look for JSON in the response
        try:
            # Extract JSON from the response (might be embedded in text)
            json_start = response_text.find('{')
            json_end = response_text.rfind('}') + 1
            print(response_text)
            if json_start != -1 and json_end != -1:
                json_str = response_text[json_start:json_end]
                action_data = json.loads(json_str)

                action_type = action_data["action"]
                slot = action_data.get("slot")
                
                teammate = action_data.get("teammate")

                color = action_data.get("color")
                number = action_data.get("number")
                last_justification = action_data.get("short_explain", "")

                # Convert color string back to Color enum if present
                if color is not None:
                    if color in ["red", "yellow", "green", "white", "blue"]:
                        color = Color[color.upper()]
                    return(random.choice(valid_actions))

                print(f"{action_type}")

                # Map schema to Action class
                if action_type == "PLAY":
                    if slot is None or slot not in [0, 1, 2, 3, 4]:
                        return random.choice(valid_actions)
                    return Action(Action.ActionType.PLAY, cnr=slot)
                elif action_type == "DISCARD":
                    if slot is None or slot not in [0, 1, 2, 3, 4]:
                        return random.choice(valid_actions)
                    return Action(Action.ActionType.DISCARD, cnr=slot)
                elif action_type == "HINT_COLOR":
                    if color is None:
                        return random.choice(valid_actions)
                    if teammate is None or teammate not in ((player_nr + 1) % 3, (player_nr + 2) % 3):
                        return random.choice(valid_actions)
                    return Action(Action.ActionType.HINT_COLOR, pnr=teammate, col=color)
                elif action_type == "HINT_NUMBER":
                    if teammate is None or teammate not in ((player_nr + 1) % 3, (player_nr + 2) % 3):
                        return random.choice(valid_actions)
                    if number is None or number not in [1, 2, 3, 4, 5]:
                        return random.choice(valid_actions)
                    return Action(Action.ActionType.HINT_NUMBER, pnr=teammate, num=number)
                else: 
                    return random.choice(valid_actions)
                
        except (json.JSONDecodeError, KeyError) as e:
            print(f"Failed to parse response: {e}")
        
        # Fallback to random action
        return random.choice(valid_actions)

    def get_action(
        self, nr, hands, knowledge, trash, played, board, valid_actions, hints
    ):
        
        nr = nr
        
        current_score = sum([col[1] for col in board])
        deck_size = 50 - current_score - len(knowledge) * 5 - len(trash) 

        trash_str = ", ".join(
        f"{color.display_name} {num}" for color, num in trash
        )

        fireworks_str = ",".join(
        f"- {color.display_name}: {num}" for color, num in board
        )

        action_str = self._format_actions(valid_actions)

        current_player_knowledge = self._format_player_knowledge(knowledge, nr)

        teammate_a = (nr + 1) % len(hands)
        teammate_b = (nr + 2) % len(hands)

        teammate_a_hand = self._format_hand(teammate_a, hands)
        teammate_a_knowledge = self._format_player_knowledge(knowledge, teammate_a)
        teammate_b_hand = self._format_hand(teammate_b, hands)
        teammate_b_knowledge = self._format_player_knowledge(knowledge, teammate_b)
        
        # TODO: add default behaviour

        user_prompt = """

        You are player {nr}

        Score: {current_score}
        Deck Size: {deck_size}
        Clue Tokens: {hints}

        {instruction_prompt}

        ## Fireworks:
        *(Last card played on each stack, 0 means no card has been played on that stack yet)*
        - Current Stacks: {fireworks_str}

        ## Discard Pile:
        - cards: {trash_str}

        ## Your Knowledge: 
        {current_player_knowledge}

        ## Teammate {teammate_a}'s Hand: 
        {teammate_a_hand}

        ## Teammate {teammate_a}'s Knowledge:
        {teammate_a_knowledge}

        ## Teammate {teammate_b}'s Hand:
        {teammate_b_hand}

        ## Teammate {teammate_b}'s Knowledge:
        {teammate_b_knowledge}

        ## Valid Actions (choose ONE):
        {action_str}
        """

        if self.use_h_conventions:
            user_prompt = h_group_prompt + user_prompt

        user_prompt_filled = user_prompt.format(nr=nr,
                current_score=current_score,
                deck_size=deck_size,
                hints=hints,
                fireworks_str=fireworks_str,
                trash_str=trash_str,
                current_player_knowledge=current_player_knowledge,
                teammate_a=teammate_a,
                teammate_a_hand=teammate_a_hand,
                teammate_a_knowledge=teammate_a_knowledge,
                teammate_b=teammate_b,
                teammate_b_hand=teammate_b_hand,
                teammate_b_knowledge=teammate_b_knowledge,
                action_str=action_str,
                instruction_prompt=shorter_instruction_prompt)
        
   
        try:
            # Call DeepSeek R1 API

            response = self.client.chat.completions.create(
                model="deepseek-reasoner",
                messages=[
                    {"role": "system", "content": shorter_system_prompt},
                    {"role": "user", "content": user_prompt_filled}
                ],
                temperature=0.1,  # Low temperature for consistent reasoning
                max_tokens=4000,  # Allow for long chain-of-thought
                stream=False
            )
            
            # Parse the response
            action = self._parse_response(nr, response.choices[0].message.content, valid_actions)
            return action
            
        except Exception as e:
            print(f"API call failed: {e}")
            return random.choice(valid_actions)
        
    def inform(self, action, player, game):
        """Update the agent based on game events"""
        # You might want to maintain conversation history or update internal state
        self.conversation_history.append({
            "player": player,
            "action": action,
            "reasoning": self.last_justification
        })
    

