#!/usr/bin/env python3

"""
Log Parser Command Line Interface.

Usage examples:

    python log_analyzer.py --help
"""

import argparse
import re
import json
from pathlib import Path
from typing import Tuple

from pandas.core.internals.construction import to_arrays

ALLOWED_SUBDIRS = {"low_scores", "max_score"}

# ---------------------------------------------------------------------------
# Command: critical_discards
# ---------------------------------------------------------------------------

def get_critical_discards_from_file(path: Path) -> Tuple[int, int]:
    """
    Return an (int, int) tuple:
    - result[0] is the total number of discards
    - results[1] is the number of critical discards
    """
    assert path.is_file(), f"The path provided is not a file: {path}"
    with open(path, "r") as f:
        lines = f.readlines()
        total_discards = sum(1 for line in lines if "Move" in line and "discards" in line)
        critical_discards_lines = [line for line in lines if "Critical Discards" in line]
        critical_discards = 0
        for line in critical_discards_lines:
            match = re.search(r"Critical Discards:\s*(\d+)", line)
            assert match
            critical_discards += int(match.group(1))

    return total_discards, critical_discards


def report_critical_discards(path: Path) -> None:
    """
    Report stats on critical discards.
    Is path points to a single log file, report stats on the single game.
    If path points to a directory of log files, report aggregate stats on all games.
    """
    if path.is_file():
        print(f"Reporting critical discards for file: {path}")
        total_discards, critical_discards = get_critical_discards_from_file(path)
        print("Total discards:", total_discards)
        print("Critical discards:", critical_discards)
        print("Critical discards ratio:", critical_discards / total_discards)

    elif path.is_dir():
        print(f"Reporting aggregate critical discards for directory {path}")
        aggregate_total_discards, aggregate_critical_discards = 0, 0
        game_count = 0
        for file in path.rglob("*"):
            if file.is_dir():
                assert file.name in ALLOWED_SUBDIRS, (f"The path under directory {path} is not a file: {file}, "
                                                      f"and does not correspond to an allowed subdirectory name")
                continue
            game_count += 1
            total_discards, critical_discards = get_critical_discards_from_file(file)
            aggregate_total_discards += total_discards
            aggregate_critical_discards += critical_discards
        print("Aggregate total discards:", aggregate_total_discards)
        print("Aggregate critical discards:", aggregate_critical_discards)
        print("Aggregate critical discards ratio:", aggregate_critical_discards / aggregate_total_discards)
        print("Number of games:", game_count)
        print("Average total discards per game:", aggregate_total_discards / game_count)
        print("Average critical discards per game:", aggregate_critical_discards / game_count)

    else:
        raise ValueError(f"Path does not exist: {path}")


# ---------------------------------------------------------------------------
# Command: hint_types
# ---------------------------------------------------------------------------

def get_hint_types_from_json(path: Path) -> Tuple[int, int, int, int]:
    """
    Given a JSON file representing a game log, return a tuple where:
    - result[0] is the total number of hints given in the game
    - result[1] is the number of intentional hints given in the game
    - result[2] is the number of redundant hints given in the game
    - result[3] is the number of random hints given in the game
    """
    assert path.is_file() and path.suffix.lower() == ".json", f"The path provided is not a JSON file: {path}"
    with open(path, "r") as f:
        json_data = json.load(f)
        assert type(json_data) == dict, f"Impossible to parse the JSON file into a dict: {path}"
        turns = 1
        total_hints = 0
        intentional_hints = 0
        redundant_hints = 0
        random_hints = 0
        for turn in json_data["actions"]:
            action = turn[f"turn_{turns}"]["action"]
            # validate the logic in the log
            # 1. there are valid intentional hints ==> we either hint the color or the rank
            if action["valid_hints"]:
                assert action["type"] == "HINT_COLOR" or action["type"] == "HINT_NUMBER", f"file: {path}"
                total_hints += 1
                intentional_hints += 1
            # 2. no valid intentional hints ==> we either have redundant hints, or we chose to play or discard
            else:
                if action["redundant_hints"] and (action["type"] == "HINT_COLOR" or action["type"] == "HINT_NUMBER"):
                    total_hints += 1
                    redundant_hints += 1
                elif action["type"] == "HINT_COLOR" or action["type"] == "HINT_NUMBER":
                    total_hints += 1
                    random_hints += 1
            turns += 1

    return total_hints, intentional_hints, redundant_hints, random_hints


def report_hint_types(path: Path) -> None:
    """
    Generate a summary of the hint types provided in the JSON logs.
    Is path points to a single log file, report hint details on the single game.
    If path points to a directory of log files, report aggregate hint details on all games.
    """

    if path.is_file():
        print(f"Reporting hint details on file: {path}")
        total_hints, intentional_hints, redundant_hints, random_hints = get_hint_types_from_json(path)
        print("Total hints:", total_hints)
        print("Intentional hints:", intentional_hints)
        print("Redundant hints:", redundant_hints)
        print("Random hints:", random_hints)
        print("Intentional hints ratio:", intentional_hints / total_hints)
        print("Redundant hints ratio:", redundant_hints / total_hints)

    elif path.is_dir():
        print(f"Reporting aggregate hint details for directory: {path}")
        aggregate_total_hints, aggregate_intentional_hints, aggregate_redundant_hints, aggregate_random_hints = 0, 0, 0, 0
        game_count = 0
        for file in path.iterdir():
            assert file.is_file()
            total_hints, intentional_hints, redundant_hints, random_hints = get_hint_types_from_json(file)
            aggregate_total_hints += total_hints
            aggregate_intentional_hints += intentional_hints
            aggregate_redundant_hints += redundant_hints
            aggregate_random_hints += random_hints
            game_count += 1

        print("Aggregate total hints", aggregate_total_hints)
        print("Aggregate intentional hints", aggregate_intentional_hints)
        print("Aggregate redundant hints", aggregate_redundant_hints)
        print("Aggregate random hints", aggregate_random_hints)
        print("Total games:", game_count)
        print("Intentional hint ratio over all games:", aggregate_intentional_hints / aggregate_total_hints)
        print("Redundant hint ratio over all games:", aggregate_redundant_hints / aggregate_total_hints)
        print("Random hint ratio over all games:", aggregate_random_hints / aggregate_total_hints)

    else:
        raise ValueError(f"Path does not exist: {path}")


# ---------------------------------------------------------------------------
# Command: third_player_hints
# ---------------------------------------------------------------------------

# TODO: implement this
def report_third_player_hints(path: Path) -> None:
    """
    Report information on the scenario where the current player hints the player after the next ("third player hints").
    The information provided is as follows:
    - Total number of hints given
    - Number of times a third player hint is provided
    - Number of times a third player hint causes the player in between to misplay
    - Number of times a third player hint causes the player in between to discard a critical card
    """

    if path.is_file():
        print(f"...: {path}")

        # TODO

    elif path.is_dir():
        print(f"...: {path}")

        # TODO

    else:
        raise ValueError(f"Path does not exist: {path}")


# ---------------------------------------------------------------------------
# Argument parser setup
# ---------------------------------------------------------------------------

def create_parser() -> argparse.ArgumentParser:
    """
    Create and configure the command-line argument parser.
    """
    parser = argparse.ArgumentParser(
        prog="log_analyzer",
        description=(
            "Parse and analyze log files using one of the provided commands. "
            "The input can be a path to a log file or a directory containing only log files, "
            "based on the appropriate command."
        ),
        epilog=(
            "Examples:\n"
            "  log_analyzer --help"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(
        dest="command",
        required=True,
        title="commands",
        description="Available log analyzer commands",
    )

    # Critical discards command: report the stats on critical discards per game or per set of games
    critical_discards_parser = subparsers.add_parser(
        "critical_discards",
        help="Report stats on critical discards."
             "If a path to a log file is passed as an argument, it will report stats on the single game."
             "If a path to a directory of log files is passed as an argument,"
             "it will report aggregate stats on the all games.",
        description="Report stats on critical discards.",
    )
    critical_discards_parser.add_argument(
        "path",
        type=Path,
        help="Path to a log file or directory of log files.",
    )
    critical_discards_parser.set_defaults(func=report_critical_discards)

    # Hint types command: report information on the types of hints provided (intentional vs redundant)
    hint_types_parser = subparsers.add_parser(
        "hint_types",
        help="Report details on the type of hints provided (intentional vs redundant).",
        description="Report details on the hints provided. "
                    "If a path to a JSON log file is passed as an argument, it will provide hint information the single game."
                    "If a path to a directory of JSON log files is passed as an argument,"
                    "it will report aggregate information on the all games.",
    )
    hint_types_parser.add_argument(
        "path",
        type=Path,
        help="Path to a JSON log file or directory of JSON log files.",
    )
    hint_types_parser.set_defaults(func=report_hint_types)

    # Third player hint command: analysis of the cases with a third player hint
    third_player_hints_parser = subparsers.add_parser(
        "third_player_hints",
        help="Analyze the effect of hinting the third player.",
        description="Report on the effect of hinting the third player. "
                    "If a path to a log file is passed as an argument, it will analyze hint information the single game."
                    "If a path to a directory of log files is passed as an argument,"
                    "it will analyze aggregate information on the all games."
    )

    third_player_hints_parser.add_argument(
        "path",
        type=Path,
        help="Path to a log file or directory of log files.",
    )

    third_player_hints_parser.set_defaults(func=report_third_player_hints)

    return parser


def main() -> int:
    parser = create_parser()
    args = parser.parse_args()

    try:
        args.func(args.path)
    except ValueError as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    main()