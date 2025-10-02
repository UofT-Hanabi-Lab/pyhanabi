general_system_prompt = """You are playing the card game Hanabi, the three player variant. Every turn I will
give you the state of the game, the actions that your teammates just took, your
teammates hands, and your hand. You will then need to choose an action to take
based on the state of the game.
# Hanabi Game Rules
## Overview and Objective:
- Hanabi is a cooperative card game in which players take turns working together
to build firework card sequences in five colors.
- Each sequence must begin with a rank 1 card and continue in increasing order up
to rank 5.
- The goal is to complete as many fireworks stacks as possible; a perfect game
scores 25 when every color stack is completed.
## Game Components:
- Deck: The deck consists of cards in five colors (Red, Yellow, Green, White,
Blue). For each color there are three copies of rank 1, two copies of rank 2,
two copies of rank 3, two copies of rank 4, and only one copy of the rank 5
card.
- Clue Tokens: There are 3 clue tokens available. These are spent when giving
clues and can be regained by discarding a card or playing a 5.
- Life Tokens: There are 8 life tokens available. Each misplayed card causes the
loss of one life token; if all three are lost, the game ends immediately, and
all players lose.
- Firework Stacks: There is one stack for each color. Cards are added to these
stacks in ascending order.
- Discard Pile: A common area where discarded or misplayed cards are placed that
all players can see.
- Player Hands: Each player’s hand is arranged so that other players can see the
cards, but the owner cannot see their own cards. So you can't see the identies
of your own cards, but you know the identies of your teammates cards.
- Deck Draw Pile: The remaining deck from which new cards are drawn.
## Game Turn and Actions:
- On each turn, a player must take one of the three following actions (Give a
Clue, Discard a Card, or Play a Card).
30
Ad-Hoc Human-AI Coordination Challenge
- The other teammates in the game are Teammate 0 and Teammate 1. After your turn,
Teammate 0 will take their turn, and then Teammate 1 will take their turn after
Teammate 0.
- After Teammate 1 takes their turn, you will take your turn again, and the game
continues in this way until the game ends.
## Give a Clue:
- Provide information about either all cards of a specific color or all cards of
a specific rank in one of your teammates hands.
- The clue will identify every card in the teammates hands that matches the given
clue information (color or rank).
- This action consumes 1 clue token.
## Discard a Card:
- Choose one card from your hand to discard.
- This action will regain 1 clue token (up to a maximum of 8).
- This action will draw a new card from the deck if one is available.
## Play a Card:
- Choose one card from your hand and attempt to play it on the corresponding
firework stack.
- If the card is the next rank number in sequence (or a rank 1 card for an empty
stack), the play is successful and the card is added to the stack.
- If the card played is of rank 5, 1 clue token is regained for the team (if not
already at the maximum).
- If the card does not match the required sequence, it is a misplay: The team
loses one life token and the card is discarded.
- The game ends immediately with a score of 0 if all three life tokens are lost
(bad).
- This action will draw a new card from the deck if one is available.
## Card Positions:
- Slots: Your hand comprises cards with slots 0, 1, 2, 3, 4, with slot 4 as the
leftmost card and slot 0 as the rightmost. The order of all the slots are:
- slot 4: leftmost, slot 3: second leftmost, slot 2: middle card, slot 1:
second rightmost, slot 0: rightmost.
- After play/discard: When a player plays or discards a card from slot X in their
hand, the card is removed from the hand, and all cards in higher-numbered slots
are shifted down (to the right) one slot.
- New cards: Any drawn card enters into slot 4 (the leftmost position).
## Game End Conditions:
- When the deck is empty, each player gets one final turn, including the player
that drew the last card.
- The game ends immediately if all three life tokens are lost, and the players
get a score of 0 (very bad).
- After the final round (once the deck is exhausted and all players have taken
their last turn), the game ends.
- A perfect game occurs if all five firework stacks are completed up to card rank
5 (score 25).
## Scoring:
- If all three life tokens are lost, the game ends with a score of 0 (very bad).
31
Ad-Hoc Human-AI Coordination Challenge
- Otherwise, the final score is the sum of the highest played rank card on each
firework pile.
- The maximum possible score is 25, achieved when every fireworks stack is
completed.
## Possible Actions:
When you take an action, here are all of the possible actions you may take:
- Discard card in slot 0 from your hand
- Discard card in slot 1 from your hand
- Discard card in slot 2 from your hand
- Discard card in slot 3 from your hand
- Discard card in slot 4 from your hand
- Play card in slot 0 from your hand
- Play card in slot 1 from your hand
- Play card in slot 2 from your hand
- Play card in slot 3 from your hand
- Play card in slot 4 from your hand
- Clue Red to Teammate 0
- Clue Yellow to Teammate 0
- Clue Green to Teammate 0
- Clue White to Teammate 0
- Clue Blue to Teammate 0
- Clue Red to Teammate 1
- Clue Yellow to Teammate 1
- Clue Green to Teammate 1
- Clue White to Teammate 1
- Clue Blue to Teammate 1
- Clue Rank 1 to Teammate 0
- Clue Rank 2 to Teammate 0
- Clue Rank 3 to Teammate 0
- Clue Rank 4 to Teammate 0
- Clue Rank 5 to Teammate 0
- Clue Rank 1 to Teammate 1
- Clue Rank 2 to Teammate 1
- Clue Rank 3 to Teammate 1
- Clue Rank 4 to Teammate 1
- Clue Rank 5 to Teammate 1 """

h_group_prompt = """
For experiments with convention-aware agents—and to mirror the play of our human-proxy agent—we include the Level
1 H-Group conventions1, a small, community-agreed protocol that teaches players to share just enough information to
coordinate safely. These rules tell an agent how to signal “this card is safe to play next” or “don’t discard this card,” and
they precisely define which card in your hand each hint refers to. By using these rules, every agent (LLM or human-proxy)
speaks the same simple clue vocabulary, letting us measure exactly how much these rules improve teamwork.
When you choose an action to take, always use the following convention rules as
the shared protocol for giving and interpreting clues---so you and your teammate
can coordinate discards, saves, and plays unambiguously. The following rules are
written with respect to you, but the same rules apply to your teammates. The
rules are written in the first person, but they apply to all players.

# Conventions Rules
## Chop:
- Definition: Your chop is the rightmost card (smallest slot value) in your hand
that has not received any clues.
- Instructions: When forced to discard, always discard your chop. If a card in
your hand has been clueed as useless (and you can clearly tell it won't help
because it's already been played), you may discard that card instead of the
chop.
- Reminder: If the rightmost slots of your hand (0, 1, etc) have received clues,
then those slots are NOT your chop, your shop is the rightmost card that has
not received any clues.
## Clue Interpretation:
- (Card slot position reminder): Your hand comprises cards with 5 different
slots, with slot 4 as the leftmost card and slot 0 as the rightmost. The order
of all the slots are:
- slot 4: leftmost, slot 3: second leftmost, slot 2: middle card, slot 1:
second rightmost, slot 0: rightmost.
- Single Card Focus: When a clue touches two or more cards, it conveys
information about only one specific card|the focused card; non-focused cards
receive no actionable instruction. The focus card must always be either a Save
Clue or a Play Clue.
- New Cards: Cards are \new" if they had no clues on them prior to this clue.
- Instructions for determining which card is the focus when a clue touches
multiple cards:
1. One New Card: If exactly one card is newly clued (had no prior clues), that
card is the focus of the clue.
2. Multiple New Cards (chop focus): If more than one card is newly clued and
the chop is included in the clue, the chop card is the focus.
3. Multiple New Cards (not including chop): If more than one card is newly
clued and the chop is not included in the clue, the leftmost new card is the
focus.
4. No New Cards: If the clue only touches cards that already had clues, the
leftmost re-clued card is the focus.
- Clue Type:
- If the chop is included in the clue, the chop card is the focus and it is
either a playable card (if it’s a Play Clue) or a critical card (if it’s a
Save Clue).
- If the chop card is not touched by the clue, the focus card (leftmost newly
clued card) is a Play Clue or a Delayed Play Clue.
## Play Clues:
- Play Clue (Direct):
- Definition: A clue given to signal that the focused card is immediately
playable right now (it is the next needed card on its firework stack).
- Instructions: If the chop card is not touched by a clue, then the focus card
is always the leftmost card, and it is always a Play Clue. When giving a Play
Clue, ensure that the focused card will fit directly onto its firework. The
Play Clue tells your teammate that their focused card is playable right now.
- Instructions: If the chop card is touched by a clue, then the focus card can
either be a Play Clue or a Save Clue, it's up to the player to figure out
which type of clue it is based on what cards are critical.
- All Play Clues are interpreted as potential Delayed Play Clues.
- Delayed Play Clue:
- Definition: A clue given to a card that is not immediately playable because
an earlier card that has received a Play Clue has not been played yet;
however, once that missing card is played, the clued card will become
playable.
- Instructions: When giving a Delayed Play Clue, make sure that the missing
card will be played soon by either yourself or your teammate. Interpret any
such clue as a promise that, after the necessary preceding card is played,
the clued card will be safe to play.
## Critical Cards:
- Definition: A Critical Card is the last copy of a card of a color and rank
combination that hast not been discarded yet, where discarding this critical
card makes it impossible to achieve a perfect score.
- Examples: A 5 (only one copy in each color), a unique rank 1 card (if both
other copies are have been discarded), or any rank 2, 3, or 4 card whose other
copy has been discarded.
- Instructions: Always treat critical cards as high priority for saving. If a
critical card becomes the chop card, it must receive a Save Clue to ensure it
isn't discarded.
## Save Clues:
- Definition: Clues used to protect critical cards from being discarded. Save
Clues can only be given to cards on the chop.
- Instructions:
- Save Clues can only be given to cards on the chop.
- If a clue touches the chp card, it is either a Save Clue or a (Delayed) Play
Clue. It's up to you to figure out which type of clue it is based on what
cards are critical.
- Use Save Clues to safeguard cards that are vital for a perfect score of 25.
- Critical Save: A clue given to a critical card on the chop to save it from
being discarded. You can give a Critical Save clue with eithr a color or a
number clue.
- 5 Save: When saving a 5 card on the chop, you must always give a rank 5 clue
to indicate that the clue is a 5 Save, not a color clue because a color clue
could be interpreted as a play clue.
- 2 Save: All rank 2 cards on the chop should be saved with a 2 Save clue if
it's the only copy of that card visible in any players hand, even if 2's are
not critical. When saving a rank 2 card on the chop, always give a rank 2
clue to indicate that the card is a 2 Save, a because a color clue could be
interpreted as a Play Clue.
- If a clue touches any card that is not on the chop, interpret it as a
(Delayed) Play Clue, not a Save Clue.
- When receiving a Save Clue on your chop, do not discard that card|keep it
safe until it becomes playable.
- All Save Clues, Critical Save Clues, 5 Saves, and 2 Saves can only be given
to cards on the chop.
## The Three Main Principles:
1. Good Touch Principle: Only give clues to cards that are have not been played
yet; avoid clueing cards that have already been played.
2. Save Principle: Including cards that are saved with Save Clues, do not allow
other players to discard playable cards. All cards that are playable need to be
"protected" by giving them a Play Clue. The following cards must not be
discarded: All rank 5 cards, Unique rank 2 cards with only one copy visible,
Critical cards with only one copy left undiscarded, and Unique playable cards
that are the only copy currently visible.
3. Minimum Clue Value Principle: Every clue must either make one or more cards
safely playable or prevent the discard of a critical card. If a clue does not
make a card playable or prevent the discard of a critical card, you should
discard instead of wasting a clue.
## The Early Game:
- Definition: The phase before any player has ever discarded their chop card.
- Instructions:
- During this phase, use every available Play Clues and Save Clues to protect
critical cards on chop (including 5 and 2 Saves).
- Only discard if there are no valid Play or Save Clue available.
- Discarding for the first time ends the Early Game and begins the Mid-Game.
## General Strategy:
- Check Teammate Chops: Always review the rightmost unclued cards in every
player’s hand to identify which ones need protection.
- Clue Selection: Prefer giving Play Clues when possible over Save Clue, as they
not only protect critical cards by giving the player something else to do
(playing the card) but also facilitate immediate or near-future plays. Use Save
Clues only when a critical card on the chop is at risk of being discarded (the
player has nothing else to do on their turn).
- Clue Type: Prefer to use color clues over rank clues for precise information
about the card’s identity unless a rnak clue can secure additional plays or
prevent a vital discard.
- Safe Discards: Discard only cards that are clearly non-critical. Protect any
card that might be needed for a perfect score.
- Identify Meaning of Clues: When it's your turn, and you're trying to interpret
clue, always follow the follwing algorithm: Identify which card slot in your
hand is the focus of the clue, and then decide on if the clue focus card is a
Play Clue or a Save Clue.
- Ever clue you give always needs to be a valid Save clue when the card you want
to save is on the chop, or a Play/Delayed Play Clue following the rules above.
## Prompts:
- Definition: A Prompt is a clue on a (currently) unplayable card, but it directs
a player to immediately play a clued card (which is the card that can be played
before the clued card) that they would not normally play right now because they
previously didn't have enough information about the cards identity.
- Instructions:
- The player receiving the prompt to play the connecting card before the clued
card can either be the player receiving the Play Clue, or any other player in
the team.
- If more than one card could be interpreted as the card that is being prompted
to play, the player being prompted should play the leftmost eligible clued
card.
- When you give a Prompt, the intended action is for the recipient to play the
prompted card as soon as possible.
- Use Prompts sparingly and only when you are confident that the focused card
is safe to play without further clues.
## Finesse:
- Definition: A move where a clue to one player implies that another player must
blind-play the connecting lower card (one rank below) from their Finesse
Position (leftmost unclued slot) even though it has no clues.
- Finesse Position: The card slot containing a player’s leftmost unclued card;
this position slides right whenever leftmost cards receive clues
- Trigger: You see an unplayable card clued as a Play Clue. If the required
lower-rank card is not visible anywhere with clues (the clue is a prompt),
assume the player immediately before the clued card holds it in their Finesse
Position and must blind-play it.
- Priority: Prompts override Finesses. If you must choose between playing a
prompted card and blind playing a card in finesse position, play the prompted
card first.
- Urgency: Blind-play into a Finesse immediately to resynchronise team knowledge;
delaying risks desynchronised information.
- Instructions (for the finessed player that needs to blind-play their finessed
card):
1. Identify your current Finesse Position (leftmost unclued slot).
2. Blind-play that card at once, assuming it is the connecting card 1 rank
below the clued card.
- Instructions (for the clue-giver):
- You can only give a finesse clue to Teammate 1, which would trigger Teammate
0 to blind-play their card in their Finesse Position before Teamamte 1's
turn.
- Ensure the clued higher card is unplayable and that the card 1 rank below
should exist in Teammate 0's Finesse Position.
- Give the higher card a clue (usually its color or rank) that unmistakably
marks it as a Play Clue.\n
"""

instruction_prompt = """
# Your Instruction:
Please consider all of the Rules and the current Game State, and decide on the
best action to take from the "Valid Actions" list.
You cannot play or discard cards from your teammate's hand. Only play a card from
your hand if you are certain it is playable based on hints or deduction based on
the rules. Check fireworks status before playing. When hints are available for
your cards (e.g., 'Colour Hint: Blue' or 'Number Hint: 3'), use them. Evaluate
possibilities like 'Colours: [Blue]' or 'Ranks: [3]'. When only one life remains,
be extremely cautious about playing cards.

# Response Format
You MUST output responses strictly in JSON format. Adhere EXACTLY to the JSON
schema and content requirements provided below.

# JSON Schema:
Schema:
{
  "action": "PLAY" | "DISCARD" | "HINT_COLOR" | "HINT_NUMBER",
  "slot": null | 0 | 1 | 2 | 3 | 4,
  "teammate": null | 0 | 1,
  "color": null | "red" | "yellow" | "green" | "white" | "blue",
  "number": null | 1 | 2 | 3 | 4 | 5,
  "confidence": 0.0-1.0,
  "short_explain": "one-line justification"
}
"""



