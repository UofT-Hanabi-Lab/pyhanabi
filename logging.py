import argparse
import os
import hashlib
import re
import ast
import json
from datetime import datetime


# TODO: we are only certain about red and yellow. Must check all others by putting the file on HanabLive
STRING_TO_SUITINDEX_MAP = {
    'red': 0,
    'yellow': 1,
    'green': 2,
    'blue': 3,
    'white': 4
}

ACTION_TYPE_TO_INDEX = {
    'play': 0,
    'discard': 1,
    'color-hint': 2,
    'rank-hint': 3,
    'end-game': 4
}


def raw_to_json(ifile: str) -> str:
    """Convert a raw game log to a set of json files formatted as required by Hanab Live.

    This function will create a subdirectory under json_logs named after the input file (ifile).
    This subdirectory will contain a JSON file for each game present in the raw input file.
    If a directory named as ifile already exists, this function will print a warning and deduplicate the names.

    @parameters:
    - ifile: input raw file to parse

    @returns: the name of the subdirectory under json_logs containing all logs for this ifile
    """
    assert os.path.isfile(ifile), f"{ifile} does not exist. Please provide a valid path."
    # Prepare output directory. Handle name duplicates
    in_file_name = os.path.basename(ifile)
    cwd = os.getcwd()
    output_dir = os.path.join(cwd, "json_logs", in_file_name)
    if os.path.isdir(output_dir):
        timestamp = datetime.now().isoformat()
        hash_suffix = hashlib.sha1(timestamp.encode()).hexdigest()[:8]
        output_dir = os.path.join(cwd, "json_logs", f"{in_file_name}_{hash_suffix}")
        assert not os.path.isdir(output_dir), ("Failed to deduplicate the filename, as a directory under json_logs with"
                                               f"the name {in_file_name} already exists."
                                               "Please choose a filename that is not yet in use.")
    os.makedirs(output_dir, exist_ok=True)

    game_count = 1
    # Parse the input file
    with open(ifile, "r") as f:
        file_content = f.read()

    single_game_pattern = re.compile(
        r"^NEW:.*?(?=^NEW:|\Z)",
        flags=re.DOTALL | re.MULTILINE
    )

    all_games = single_game_pattern.findall(file_content)
    for i, game_log in enumerate(all_games):
        log_dict = {}
        lines = game_log.strip().splitlines()
        if len(lines) < 3:
            print(f"WARNING: skipping game {i} as its log not contain enough information to translate into json")
            continue

        # Parse the number of players from the first line
        header_match = re.match(r"^NEW: starting a new game of (\d+) players with the following deck:", lines[0])
        assert header_match
        num_players = int(header_match.group(1))
        log_dict['players'] = [f"Player {i + 1}" for i in range(num_players)]

        # Parse the initial deck from the second line
        try:
            deck_list = ast.literal_eval(lines[1])
            if not isinstance(deck_list, list):
                raise ValueError("Parsed object is not a list")
        except (SyntaxError, ValueError) as e:
            print("Invalid deck format:", e)
            exit(1)
        log_dict['deck'] = [{"suitIndex": STRING_TO_SUITINDEX_MAP[c], "rank": r} for c, r in deck_list]

        # Parse all actions taken in the game from the third line onwards
        play_pattern = re.compile(r"^Turn\s+\d+:\s+Player\s+(?P<pnr>\d+)\s+plays\s+their\s+(?P<card_idx>\d+)$")
        discard_pattern = re.compile(r"^Turn\s+\d+:\s+Player\s+(?P<pnr>\d+)\s+discards\s+their\s+(?P<card_idx>\d+)$")
        color_hint_pattern = re.compile(
            r"^Turn\s+\d+:\s+Player\s+(?P<source_pnr>\d+)\s+hints\s+player\s+(?P<target_pnr>\d+)"
            r"\s+about\s+all\s+their\s+(?P<value>[A-Za-z]+)\s+cards$"
        )
        rank_hint_pattern = re.compile(
            r"^Turn\s+\d+:\s+Player\s+(?P<source_pnr>\d+)\s+hints\s+player\s+(?P<target_pnr>\d+)"
            r"\s+about\s+all\s+their\s+(?P<value>\d+)$"
        )
        patterns = [
            ('play', play_pattern),
            ('discard', discard_pattern),
            ('color-hint', color_hint_pattern),
            ('rank-hint', rank_hint_pattern)
        ]
        log_dict['actions'] = []
        num_turns = len(lines) - 2
        for index, action_line in enumerate(lines[2:]):
            line_matched = False
            for action_name, action_re in patterns:
                match = action_re.match(action_line)
                if match:
                    line_matched = True
                    if action_name in {'play', 'discard'}:
                        action_info = {
                            "type": ACTION_TYPE_TO_INDEX[action_name],
                            "target": match.group("card_idx")
                        }
                    else:  # action name in {'color-hint', 'rank-hint'}
                        action_info = {
                            "type": ACTION_TYPE_TO_INDEX[action_name],
                            "target": match.group("target_pnr"),
                            "value": match.group("value")
                        }
                    if index == num_turns + 1:
                        # Because the first two lines contain other data,
                        # the last action will be found at index num_turns + 1
                        action_info["type"] = ACTION_TYPE_TO_INDEX['end-game']
                    log_dict['actions'].append(action_info)
            if not line_matched:
                print(f"The following line was not formatted correctly: {action_line}")
                exit(1)

        # Open a new file in the output folder for the current game and dump data to it
        outfile_path = os.path.join(cwd, 'json_logs', in_file_name, f'game_{game_count}.json')
        with open(outfile_path, "w") as f:
            json.dump(log_dict, f)

        game_count += 1

    return os.path.basename(output_dir)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="A module to convert raw experiment logs into individual game logs"
                    "in the json format accepted by Hanab Live"
    )
    parser.add_argument("ifile",
                        help="The path to the raw input file which contains the result of logging the experiment"
                             "using the --log flag")

    args = parser.parse_args()
    print(f"Converting file {args.ifile} to a valid json format...")
    out_dir = raw_to_json(args.ifile)
    print(f"Conversion completed. Yay!")
    print(f"You can find all files under the json_logs/{out_dir} directory")
