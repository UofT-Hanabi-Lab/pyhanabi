import numpy as np
import re
import os
from openai import OpenAI
import pandas as pd
import datetime
from fuzzywuzzy import process
from typing import override

from players import Player
from utils import Action, Color


def add_to_dict_list(dictionary, key, item):
    if key not in dictionary:
        dictionary[key] = [item]
    else:
        dictionary[key].append(item)


class bcolors:
    HEADER = "\033[95m"
    OKBLUE = "\033[94m"
    OKCYAN = "\033[96m"
    OKGREEN = "\033[92m"
    WARNING = "\033[93m"
    FAIL = "\033[91m"
    ENDC = "\033[0m"
    BOLD = "\033[1m"
    UNDERLINE = "\033[4m"


class LLMAgentPlayer(Player):
    def __init__(
        self,
        name,
        pnr,
        model="deepseek-chat",
        use_verification=True,
        use_interpretation=True,
    ):
        super().__init__(name, pnr)
        self.player_id = pnr
        self.player_names = ["Player 0", "Player 1", "Player 2"]
        self.model = model
        self.use_verification = use_verification
        self.use_interpretation = use_interpretation

        if "gpt" in self.model:
            self.model_type = "openai"
        else:
            self.model_type = "mistral"

        self.client = OpenAI(
            api_key=os.getenv("OPENAI_API_KEY"), base_url="https://api.deepseek.com"
        )

        self.time_stamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        self.action_regex = r"Action:\s*(.*)"

        self.color_name_map = {
            Color.RED: "Red",
            Color.YELLOW: "Yellow",
            Color.GREEN: "Green",
            Color.WHITE: "White",
            Color.BLUE: "Blue",
        }

        self.llm_system_prompt = "You are a helpful assistant."

        self.rules = """
        - The game uses a 50-card deck, divided into five colours (red (R), green (G), blue (B), yellow (Y), white (W)). Each color has cards of ranks 1 to 5. Each color has with three 1's, two 2's, two 3's, two 4's, one 5.
        - Players have to create stacks of each color. Each color stack starts with a Rank 1 card and goes up one by one in ascending order up to Rank 5.  (e.g. Red Stack should go from R1 -> R2 -> R3 -> R4 -> R5). A card can only be played if it is the next in the incremental sequence for its color stack.
        - Players can only see the other's hand, not their own.
        - Players have plausible knowledge of their cards based on previously provided hints by the other player
        - They can either play a card, give a hint (reveal), or discard a card.
        ***Actions:***
                1. Hint (Clue): Spend a hint token to reveal cards with a particular color or rank. Revealing a color reveals all cards of that color in partner's hand. Revealing a rank reveals all cards with that rank in partner's hand. The game starts with 8 hint tokens. If no token left, no more hints can be given. 
                2. Discard: Discard a card to regain a hint token and draw a new card. 
                3. Play a Card: If a card played follows sequence in its color stack, it succeeds. Success of rank 5 card in any stack gives an additional hint token. Failure discards the card and loses a life. Playing a card you are unsure about is risky as it costs a life.
        ***The game ends when: (three options) ***
                - All five stacks are completed. 25 Points. 
                - Three lives have been lost. 0 Points no matter how many cards have been placed in the stack. 
                - After the last card from the deck is drawn and each player has had a final turn. Sum total of the top card ranks of each color stack. 
        """

        self.conventions = """
        1. **Card Layout:**
            - Cards are indexed from 0 to 4 (5 cards per hand).
            - Card slots are referenced by their index (0-4).
        2. **Clues:**
            - Two types of clues: Play Clue (play the card) and Save Clue (save for later).
            - If a Play Clue or Save Clue can't be given, players must discard.
        3. **Play Clue:**
            - A play clue is revealing a card or cards in partners hand that are immediately playable on the stack by indicating their rank or color.
        4. **Save Clue**
            - A save clue is used to save rank 5 cards, unique rank 2 cards and critical cards (only one of the kind left) 
        5. **Prioritize Play Clues over Save Clues:**
            - Prefer giving Play Clues if both are viable options.
        6. **Discard Without Fear:**
            - Discard confidently, as saving important cards is a team responsibility.
        7. **Play Carefully:**
            - Only play a card when you are confident it is the next card needed for its stack."""

        self.base_prompt = f"""The card game Hanabi has the following rules:
        {self.rules}
        I am {self.player_names[self.player_id]}, playing the card game Hanabi with other players. 
        At each time step I will provide you with the relevant information of the game. I will also provide you with the legal actions, help me select the best next action. Remember I am playing as {self.player_names[self.player_id]}. Format your response as Explanation: <brief explanation for selecting the move>\nAction:<selected move>. Do not say anything else. Got it?"""

        self.verifier_base_prompt = f"""The card game Hanabi has the following rules:
        {self.rules}          
        I am {self.player_names[self.player_id]}, playing the card game Hanabi with other players."""

        self.epistemologist_base_prompt = f"""The card game Hanabi has the following rules:
        {self.rules}
        I am {self.player_names[self.player_id]}, playing the card game Hanabi with other players. 
        You are a Theory of Mind inference agent for our game. You will be provided with a teammate's selected action and the current state information after they took their action. You will provide me with two things: 1. An explanation for the teammate's previous action along with their intention and implicit communication. 2. What is the best information for me to give my teammates based on their knowledge? 
        Format your response as:
        Teammate Action Explanation:<1 sentence explanation of teammate action>
        Clue Suggestion:<What information (specify rank or color) should I reveal to my teammates based on their knowledge>.
        """

        self.verifier_system_prompt = """You are an action verification agent for games. I will provide you with an action and you need to check whether the action satisfies the criteria: 1. Rule Following: It follows to the rules of the game. 2. Safety: It won't lead to the game ending immediately. Think about the action and the current state of the stack and the available hint tokens. End your response with "Verification: Okay" if selected action follows ***both*** criteria and "Verification: Not Okay" otherwise. Restrict your response to 4-5 sentences."""

        self.assistant_response_initial = """Got it!"""

        if self.model_type == "openai":
            self.base_message = [
                {"role": "system", "content": self.llm_system_prompt},
                {"role": "user", "content": self.base_prompt},
                {"role": "assistant", "content": self.assistant_response_initial},
            ]
            self.verifier_base_message = [
                {"role": "system", "content": self.verifier_system_prompt},
                {"role": "user", "content": self.verifier_base_prompt},
                {"role": "assistant", "content": self.assistant_response_initial},
            ]
            self.epistemologist_message = [
                {"role": "user", "content": self.epistemologist_base_prompt},
                {"role": "assistant", "content": self.assistant_response_initial},
            ]
        else:
            self.base_message = [
                {"role": "user", "content": self.llm_system_prompt + self.base_prompt},
                {"role": "assistant", "content": self.assistant_response_initial},
            ]
            self.verifier_base_message = [
                {
                    "role": "user",
                    "content": self.verifier_system_prompt + self.verifier_base_prompt,
                },
                {"role": "assistant", "content": self.assistant_response_initial},
            ]
            self.epistemologist_message = [
                {"role": "user", "content": self.epistemologist_base_prompt},
                {"role": "assistant", "content": self.assistant_response_initial},
            ]

        self.working_memory = {}
        self.action_history = []
        self.episodic_memory = {0: [], 1: [], 2: []}
        self.log_csv_dict = {}
        self.log_dir = "logs/hanabi"

        if not os.path.exists(self.log_dir):
            os.makedirs(self.log_dir)

        self.partner_action_inference_string = ""
        self.last_actions = {0: None, 1: None, 2: None}

    @override
    def reset(self) -> None:
        self.working_memory = {}
        self.action_history = []
        self.episodic_memory = {0: [], 1: [], 2: []}
        self.log_csv_dict = {}
        self.partner_action_inference_string = ""
        self.last_actions = {0: None, 1: None, 2: None}

    def _summarize_card_knowledge(self, card_knowledge):
        """Summarize a single card slot's knowledge as a list of possible (color, rank).

        This is a non-overriding method.       
        """
        colors = list(Color)
        ranks = list(range(1, 6))
        possible = []
        for c_idx, row in enumerate(card_knowledge):
            for r_idx, count in enumerate(row):
                if count > 0:
                    possible.append((colors[c_idx], ranks[r_idx]))
        return possible

    def _get_card_knowledge(self, knowledge, player_idx):
        """
        This function summarises a player's card knowledge to input into the LLM. 

        This is a non-overriding method.
        """
        description = f"Player {player_idx}'s cards based on their knowledge:\n"
        for i, card_knowledge in enumerate(knowledge[player_idx]):
            possibilities = self._summarize_card_knowledge(card_knowledge)
            description += f"Slot {i} could be: ["
            seen_colors = set()
            for color, rank in possibilities:
                if color not in seen_colors:
                    description += f"{self.color_name_map[color]}, "
                    seen_colors.add(color)
            description = description.rstrip(", ")
            description += "] ["

            seen_ranks = set()
            for color, rank in possibilities:
                if rank not in seen_ranks:
                    description += f"{rank}, "
                    seen_ranks.add(rank)
            description = description.rstrip(", ")
            description += "]\n"

        add_to_dict_list(self.log_csv_dict, "My Card Knowledge", description)
        return description

    def _get_player_hand(self, hands, player_idx):
        """
        This function summarises a player's hand for the LLM Agent. 

        It is a non-overriding method.
        """
        description = f"Player {player_idx}'s visible cards:\n"
        hand = hands[player_idx]
        for slot, (col, num) in enumerate(hand):
            description += f"[Slot {slot}: {self.color_name_map[col]} {num}]\n"
        add_to_dict_list(self.log_csv_dict, f"Player {player_idx} Hand", description)
        return description

    def _get_current_stack(self, board):
        """
        This function summarises the current stacks for the LLM Agent.

        It is a non-overriding method.
        """
        description = "Current Stacks: "
        for color, num in board:
            description += (
                f"{self.color_name_map[color]} - {self.color_name_map[color]} {num} "
            )
        description += "\n"
        add_to_dict_list(self.log_csv_dict, "Stack", description)
        return description

    def _add_soft_constraints(self, board):
        """
        This function adds soft constraints about the next playable cards for each stack to help the LLM 
        reason about the game state better.
        
        It is a non-overriding method.
        """
        description = "The next cards that can be played on each stack are:\n"
        for color, num in board:
            if num != 5:
                description += f"Only {self.color_name_map[color]} {num + 1} can be played on {self.color_name_map[color]} stack\n"
            else:
                description += f"{self.color_name_map[color]} stack is complete. "
        add_to_dict_list(self.log_csv_dict, "Soft Constraints", description)
        description += "\n"
        return description

    def _format_actions(self, valid_actions):
        """Turn valid Action objects into a lettered list for the prompt.

        This is a non-overriding method.
        """
        formatted = []
        for i, action in enumerate(valid_actions):
            ord_letter = chr(i + 65)
            if action.action_type == Action.ActionType.PLAY:
                formatted.append(f"{ord_letter}. Play My Slot {action.cnr}.")
            elif action.action_type == Action.ActionType.DISCARD:
                formatted.append(f"{ord_letter}. Discard My Slot {action.cnr}.")
            elif action.action_type == Action.ActionType.HINT_COLOR:
                formatted.append(
                    f"{ord_letter}. Hint Player {action.pnr}'s {self.color_name_map[action.col]} color cards."
                )
            elif action.action_type == Action.ActionType.HINT_NUMBER:
                formatted.append(
                    f"{ord_letter}. Hint Player {action.pnr}'s rank {action.num} cards."
                )
        return formatted

    def _get_legal_moves(self, valid_actions):
        """
        This function summarises the legal moves for the LLM Agent.
        
        It is a non-overriding method.
        """
        self.transformed = self._format_actions(valid_actions)
        description = "Available Legal Actions:\n"
        for tm in self.transformed:
            description += tm + "\n"
        add_to_dict_list(self.log_csv_dict, "Available Actions", description)
        return description

    def _get_previous_selected_actions(self):
        """This function gets the agent's action history to send to the LLM agent.
        
        It is a non-overriding method.
        """
        if len(self.action_history) > 0:
            return (
                f"My Action History: {', '.join([ac for ac in self.action_history])}\n"
            )
        else:
            return ""

    def _infer_partner_action(self, description):
        """
        This function infers the partner's last action using Theory of Mind.

         It is a non-overriding method.
         """
        if not self.use_interpretation:
            return ""

        partner_action_inference_description = ""
        recent_actions = []

        # Collect recent actions from teammates
        for player_idx in range(len(self.player_names)):
            if (
                player_idx != self.player_id
                and self.last_actions[player_idx] is not None
            ):
                recent_actions.append((player_idx, self.last_actions[player_idx]))

        if not recent_actions:
            return ""

        # Interpret the most recent teammate action
        player_idx, action_str = recent_actions[-1]

        epistemic_message = self.epistemologist_message + [
            {
                "role": "user",
                "content": f"***Player {player_idx}'s selected action***: {action_str}\n\nMy current state information: {description}. Think step by step about their action. Think about what it implies. If I should give a clue next, think about what clue I can give.",
            }
        ]

        print(
            f"""{bcolors.OKGREEN}EPISTEMIC INPUT: ***Player {player_idx}'s action***: {action_str}{bcolors.ENDC}"""
        )

        epistemic_response_string = self.llm_inference(epistemic_message)
        partner_action_inference_description = f"Interpretation of Player {player_idx}'s Last Action: {epistemic_response_string}.\nYou can use the clue suggestion if giving a hint is the next best possible move and ignore it otherwise.\n"

        print(
            f"""{bcolors.OKGREEN}EPISTEMIC INFERENCE: {partner_action_inference_description}{bcolors.ENDC}"""
        )
        self.partner_action_inference_string = partner_action_inference_description

        add_to_dict_list(
            self.log_csv_dict,
            "Epistemic Information",
            partner_action_inference_description,
        )
        return partner_action_inference_description

    def _observation_to_description(
        self, nr, hands, knowledge, trash, board, hints, deck_size
    ):
        """
        This function converts the current observation to a text description for the LLM Agent.
        
        It is a non-overriding method.
        """
        self.working_memory["turn"] = f"It is currently My (Player {nr}) turn.\n"
        description = self.working_memory["turn"]

        self.working_memory["stack"] = self._get_current_stack(board)
        description += self.working_memory["stack"]

        self.working_memory["card_knowledge"] = self._get_card_knowledge(knowledge, nr)
        description += self.working_memory["card_knowledge"]

        # Show other players' hands and knowledge
        for player_idx in range(len(hands)):
            if player_idx != nr:
                self.working_memory[f"player_{player_idx}_hand"] = (
                    self._get_player_hand(hands, player_idx)
                )
                description += self.working_memory[f"player_{player_idx}_hand"]

                self.working_memory[f"player_{player_idx}_knowledge"] = (
                    self._get_card_knowledge(knowledge, player_idx)
                )
                description += self.working_memory[f"player_{player_idx}_knowledge"]

        self.working_memory["hint_tokens"] = f"Remaining Hint Tokens: {hints}\n"
        description += self.working_memory["hint_tokens"]

        self.working_memory["deck_size"] = f"Deck Size: {deck_size}\n"
        description += self.working_memory["deck_size"]

        trash_str = ", ".join(
            f"{self.color_name_map[color]} {num}" for color, num in trash
        )
        self.working_memory["discard_pile"] = f"The discard pile is: {trash_str}\n"
        description += self.working_memory["discard_pile"]

        self.working_memory["previous_selected_actions"] = (
            self._get_previous_selected_actions()
        )
        description += self.working_memory["previous_selected_actions"]

        self.working_memory["soft_constraints"] = self._add_soft_constraints(board)
        description += self.working_memory["soft_constraints"]

        return description

    def llm_inference(self, message):
        """
        This function gets he LLM's response.
        
        It is a non-overriding method
        """
        response = self.client.chat.completions.create(
            messages=message,
            model=self.model,
            temperature=0.6,
            top_p=1,
            frequency_penalty=0,
            presence_penalty=0,
        )
        response_string = response.choices[0].message.content
        return response_string

    def find_best_match(self, action_string):
        """
        This function finds the best matching action from the LLM's response.
        
        It is a non-overriding method.
        """
        match = re.search(self.action_regex, action_string.strip())
        if match:
            selected_match = match.group(1).strip().lower()
            if "action:" in selected_match.lower():
                updated_action_regex = r"action:\s*(.*)"
                match = re.search(updated_action_regex, selected_match.strip())
                if match:
                    selected_match = match.group(1).strip().lower()
            selected_move, score = process.extractOne(
                selected_match, [t.lower() for t in self.transformed]
            )
            # Get the original formatted version
            idx = [t.lower() for t in self.transformed].index(selected_move)
            return self.transformed[idx]
        else:
            return np.random.choice(self.transformed)

    @override
    def get_action(
        self, nr, hands, knowledge, trash, played, board, valid_actions, hints
    ):
        """Main interface method for getting agent's action"""

        print(f"\n{bcolors.HEADER}Current Player is: Player {nr}{bcolors.ENDC}")

        # Calculate deck size
        current_score = sum([col[1] for col in board])
        deck_size = 50 - current_score - len(knowledge) * 5 - len(trash)

        # Build state description
        generator_description = self._observation_to_description(
            nr, hands, knowledge, trash, board, hints, deck_size
        )

        # Add legal moves
        self.working_memory["legal_moves"] = self._get_legal_moves(valid_actions)
        temp_description = generator_description + self.working_memory["legal_moves"]

        # Interpret partner actions if enabled
        self.working_memory["partner_interpretation"] = self._infer_partner_action(
            temp_description
        )
        generator_description += self.working_memory["partner_interpretation"]
        generator_description += self.working_memory["legal_moves"]

        print(generator_description)

        # Generate action
        self.generator_message = self.base_message + [
            {"role": "user", "content": generator_description}
        ]

        add_to_dict_list(self.log_csv_dict, "State", generator_description)
        add_to_dict_list(self.log_csv_dict, "Message", str(self.generator_message))

        action_string = self.llm_inference(self.generator_message)
        print(f"""{bcolors.WARNING}LLM RESPONSE: {action_string}{bcolors.ENDC}""")
        selected_move = self.find_best_match(action_string)

        # Verification loop if enabled
        if self.use_verification:
            verification_response_string = ""
            verifier_responses = []
            verifier_description = f"State: {generator_description.replace(self.partner_action_inference_string, '')}\n\nMy Solution: {selected_move}. Think step by step. Think about rules and think about safety."
            print(
                f"""{bcolors.WARNING}VERIFIER INPUT: {verifier_description}{bcolors.ENDC}"""
            )
            self.verifier_message = self.verifier_base_message + [
                {"role": "user", "content": verifier_description}
            ]
            verification_response_string = self.llm_inference(self.verifier_message)
            verifier_responses.append(verification_response_string)
            print(
                f"""{bcolors.OKCYAN}VERIFICATION RESPONSE: {verification_response_string}{bcolors.ENDC}"""
            )

            counter = 0
            while (
                "verification: okay" not in verification_response_string.lower()
                and counter < 3
            ):
                counter += 1
                self.generator_message.append(
                    {"role": "assistant", "content": action_string}
                )
                updated_generator_message = f"Your selected action: {selected_move} is not appropriate. {verification_response_string}. Please choose another action. List of Available Actions:\n"
                for tm in self.transformed:
                    if tm.lower() != selected_move.lower():
                        updated_generator_message += tm + "\n"

                self.generator_message.append(
                    {"role": "user", "content": updated_generator_message}
                )

                action_string = self.llm_inference(self.generator_message)
                print(
                    f"{bcolors.WARNING}LLM CORRECTED RESPONSE: {action_string}{bcolors.ENDC}"
                )
                selected_move = self.find_best_match(action_string)

                self.verifier_message[-1]["content"] = (
                    f"State: {generator_description.replace(self.partner_action_inference_string, '')}\n\nMy Solution: {selected_move}. Think step by step. Think about rules and think about safety."
                )
                verification_response_string = self.llm_inference(self.verifier_message)
                verifier_responses.append(verification_response_string)
                print(
                    f"""{bcolors.OKCYAN}VERIFICATION RESPONSE: {verification_response_string}{bcolors.ENDC}"""
                )

            add_to_dict_list(
                self.log_csv_dict,
                "VERIFICATION Response",
                " ***** ".join(verifier_responses),
            )

        add_to_dict_list(self.log_csv_dict, "Generator Response", action_string)
        add_to_dict_list(self.log_csv_dict, "Selected Action", selected_move)
        self.action_history.append(selected_move.title())

        # Find matching action
        selected_move_idx = self.transformed.index(selected_move)
        final_action = valid_actions[selected_move_idx]

        add_to_dict_list(self.log_csv_dict, "Selected Action Object", str(final_action))

        # Log action to episodic memory
        self.episodic_memory[nr].append(selected_move)
        self.last_actions[nr] = selected_move

        # Save logs - pad all columns to same length
        max_len = (
            max(len(v) for v in self.log_csv_dict.values()) if self.log_csv_dict else 0
        )
        padded_dict = {
            k: v + [""] * (max_len - len(v)) for k, v in self.log_csv_dict.items()
        }
        df = pd.DataFrame(padded_dict)
        df.to_csv(f"{self.log_dir}/Player_{nr}_{self.model}_{self.time_stamp}.csv")

        return final_action

    @override
    def inform(self, action, player, game):
        """Update the agent based on game events"""
        # Convert action to string and store
        action_str = self._action_to_string(action, player)
        self.last_actions[player] = action_str
        self.episodic_memory[player].append(action_str)

    def _action_to_string(self, action, player):
        """Convert an Action object to a readable string
        
        It is a non-overriding method.
        """
        if action.action_type == Action.ActionType.PLAY:
            return f"Player {player} played Slot {action.cnr}."
        elif action.action_type == Action.ActionType.DISCARD:
            return f"Player {player} discarded Slot {action.cnr}."
        elif action.action_type == Action.ActionType.HINT_COLOR:
            return f"Player {player} hinted Player {action.pnr}'s {self.color_name_map[action.col]} color cards."
        elif action.action_type == Action.ActionType.HINT_NUMBER:
            return (
                f"Player {player} hinted Player {action.pnr}'s rank {action.num} cards."
            )
        return "Unknown action"
