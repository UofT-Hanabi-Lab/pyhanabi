from utils import Color


def make_deck_dead_color_detection():
    """
    This deck is manually constrcuted to create a scenario
    relevant to test dead color detection in the early stages of the game.
    It is constructed as follows:
    - AI hand: B1, Y1, G1, W1, R3
    - Human hand: R2, R2, R1, R1, R1

    To test the feature, the human player should make sure to play a R1,
    and discard all other initial cards, before hinting at the R3 in the AI hand.
    If dead color detection happens correctly, the AI is expected to discard the R3.

    At the moment dead color detection requires manual testing.
    This function can be used in place of make_deck() in game.py when testing for this feature.
    """
    # Artificial deck for testing
    deck = []
    deck.extend(
        [
            (Color.BLUE, 1),
            (Color.YELLOW, 1),
            (Color.GREEN, 1),
            (Color.WHITE, 1),
            (Color.RED, 3),
        ]
    )  # AI hand
    deck.extend(
        [(Color.RED, 2), (Color.RED, 2), (Color.RED, 1), (Color.RED, 1), (Color.RED, 1)]
    )  # Human hand
    # Now construct the rest of the deck
    deck.extend([(col, 5) for col in Color])  # missing 5's
    deck.extend([(col, 4) for col in Color] * 2)  # missing 4's
    deck.append((Color.RED, 3))  # only one missing red 3
    deck.extend(
        [(col, 3) for col in Color if col != Color.RED] * 2
    )  # other missing 3's
    deck.extend([(col, 2) for col in Color if col != Color.RED] * 2)  # missing 2's
    deck.extend(
        [(col, 1) for col in Color if col != Color.RED] * 2
    )  # other missing 1's
    assert len(deck) == 50
