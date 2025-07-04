from http.server import HTTPServer, BaseHTTPRequestHandler
import socketserver
import time
import shutil
import os

import random
import hashlib
import tutorial
import sys
import traceback
import consent
import threading
from cgi import parse_header, parse_multipart
from typing import override
from urllib.parse import parse_qs

from hanabi import NullStream
from utils import Action, Color, format_card
from game import Game

from players import (
    Player,
    SelfIntentionalPlayerWithMemory,
    InnerStatePlayer,
    OuterStatePlayer,
    SelfRecognitionPlayer,
    IntentionalPlayer,
    SelfIntentionalPlayer,
    SelfIntentionalPlayerDetectDeadColors,
)

from serverconf import HOST_NAME, PORT_NUMBER


HAND = 0
TRASH = 1
BOARD = 2
TRASHP = 3

debug = True


errlog = sys.stdout
if not debug:
    errlog = open("hanabi.log", "w")


template = """

<table width="100%%">
<tr><td width="15%%" valign="top"><br/>

<table style="font-size:14pt" width="100%%">
<tr><td>
<table width="100%%" style="font-size:14pt">
<tr><td width="85%%"><b>Hint tokens left:</b></td><td> %s</td></tr>
<tr><td><b>Mistakes made so far:</b></td><td> %s</td></tr>
<tr><td><b>Cards left in deck:</b></td><td> %s</td></tr>
</table>

</td>
</tr>
<tr><td>
<center><h2>Discarded</h2></center>
%s
</td></tr>
</table>
%s
</td>
<td>
<center>
<h2> Other player </h2>
<table>
<tr><td>%s<br/>%s</td>
    <td>%s<br/>%s</td>
    <td>%s<br/>%s</td>
    <td>%s<br/>%s</td>
    <td>%s<br/>%s</td>
</tr>
%s
<tr><td colspan="5"><center><h2>You</h2></center></td></tr>
<tr><td>%s<br/>%s</td>
    <td>%s<br/>%s</td>
    <td>%s<br/>%s</td>
    <td>%s<br/>%s</td>
    <td>%s<br/>%s</td>
</tr>
</table>
</center>
</td>
<td width="15%%" valign="top"><center> <h2>Actions</h2> </center><br/>
<div style="font-size:14pt">
%s
</div></td>
</tr>
</table>
"""

board_template = """<tr><td colspan="5"><center>%s</center></td></tr>
<tr><td>%s</td>
    <td>%s</td>
    <td>%s</td>
    <td>%s</td>
    <td>%s</td>
</tr>"""


def format_board(game, show, gid):
    if not game.started:
        return (
            '<tr><td colspan="5"><center><h1><a href="/gid%s/start/">Start Game</a></h1></center></td></tr>'
            % gid
        )
    title = "<h2>Board</h2>"
    if game.done():
        if game.dopostsurvey:
            title = (
                "<h2>Game End<h2>Points: "
                + str(game.score())
                + '<br/><a href="/postsurvey/%s">Continue</a>' % gid
            )
        elif game.study:
            title = (
                "<h2>Game End<h2>Points: "
                + str(game.score())
                + '<br/><a href="/new/study/%s">Play again</a>' % gid
            )
        else:
            title = (
                "<h2>Game End<h2>Points: "
                + str(game.score())
                + '<br/><a href="/restart/">New game</a>'
            )

    def make_board_image(x):
        (i, card) = x
        return make_card_image(card, [], (BOARD, 0, i) in show)

    boardcards = list(map(make_board_image, enumerate(game.board)))
    args = tuple([title] + boardcards)
    return board_template % args


def format_action(x, gid, replay=None):
    (i, (action, pnr, card)) = x
    result = "You "
    other = "the AI"
    otherp = "their"
    if pnr == 0:
        result = "AI "
        other = "you"
        otherp = "your"
    if i <= 1:
        result += " just "

    if action.action_type == Action.ActionType.PLAY:
        result += " played <b>" + format_card(card) + "</b>"
    elif action.action_type == Action.ActionType.DISCARD:
        result += " discarded <b>" + format_card(card) + "</b>"
    else:
        result += " hinted {} about all {} ".format(other, otherp)
        if action.action_type == Action.ActionType.HINT_COLOR:
            result += action.col.display_name + " cards"
        else:
            result += str(action.num) + "s"
    if i == 0:
        if debug:
            if replay:
                (gid, round, info) = replay
                explainlink = (
                    '<a href="/replay/%s/%d/explain" target="_blank">(Explain)</a>'
                    % (gid, round)
                )
            else:
                explainlink = (
                    '<a href="/gid%s/explain" target="_blank">(Explain)</a>' % gid
                )

        return "<b>" + result + "</b>%s<br/><br/>" % explainlink
    if i == 1:
        return result + "<br/><br/>"
    return '<div style="color: gray;">' + result + "</div>"


def show_game_state(game, player, turn, gid, replay=False):
    def make_ai_card(x, highlight):
        (i, (col, num)) = x

        hintlinks = [
            ("Hint Rank", "/gid%s/%d/hintrank/%d" % (gid, turn, i)),
            ("Hint Color", "/gid%s/%d/hintcolor/%d" % (gid, turn, i)),
        ]
        if replay:
            (pgid, round, info) = replay
            hintlinks = [
                ("Hint Rank", "/takeover/%s/%d/hintrank/%d" % (pgid, round, i)),
                ("Hint Color", "/takeover/%s/%d/hintcolor/%d" % (pgid, round, i)),
            ]
        if game.hints == 0 or game.done() or not game.started:
            hintlinks = []
            highlight = False
        return make_card_image((col, num), hintlinks, highlight)

    aicards = []
    for i, c in enumerate(game.hands[0]):
        aicards.append(make_ai_card((i, c), (HAND, 0, i) in player.show))
        aicards.append(", ".join(player.aiknows[i]))

    while len(aicards) < 10:
        aicards.append("")

    def make_your_card(x, highlight):
        i = x[0]
        playlinks = [
            ("Play", "/gid%s/%d/play/%d" % (gid, turn, i)),
            ("Discard", "/gid%s/%d/discard/%d" % (gid, turn, i)),
        ]
        if replay:
            (pgid, round, info) = replay
            playlinks = [
                ("Play", "/takeover/%s/%d/play/%d" % (pgid, round, i)),
                ("Discard", "/takeover/%s/%d/discard/%d" % (pgid, round, i)),
            ]
        if game.done() or not game.started:
            playlinks = []
        return unknown_card_image(playlinks, highlight)

    yourcards = []
    for i, c in enumerate(game.hands[1]):
        if game.done():
            yourcards.append(make_ai_card((i, c), False))
        else:
            yourcards.append(make_your_card((i, c), (HAND, 1, i) in player.show))
        yourcards.append(", ".join(player.knows[i]))
    while len(yourcards) < 10:
        yourcards.append("")
    board = format_board(game, player.show, gid)
    foundtrash = []
    localtrash = game.trash[:]
    localtrash.sort()
    discarded = {}
    trashhtml = '<table width="100%%" style="border-collapse: collapse"><tr>\n'
    for i, c in enumerate(Color):
        style = "border-bottom: 1px solid #000"
        if i > 0:
            style += "; border-left: 1px solid #000"
        trashhtml += (
            '<td valign="top" align="center" style="%s" width="20%%">%s</td>\n'
            % (style, c.display_name)
        )
        discarded[c] = []
        for col, num in game.trash:
            if col == c:
                if (
                    (TRASH, 0, -1) in player.show
                    and (col, num) == game.trash[-1]
                    and (col, num) not in foundtrash
                ):
                    foundtrash.append((col, num))
                    discarded[c].append('<div style="color: red;">%d</div>' % (num))
                elif (
                    (TRASH, 0, -2) in player.show
                    and (col, num) == game.trash[-2]
                    and (col, num) not in foundtrash
                ):
                    foundtrash.append((col, num))
                    discarded[c].append('<div style="color: red;">%d</div>' % (num))
                else:
                    discarded[c].append("<div>%d</div>" % num)
        discarded[c].sort()
    trashhtml += '</tr><tr style="height: 150pt">\n'
    for i, c in enumerate(Color):
        style = ' style="vertical-align:top"'
        if i > 0:
            style = ' style="border-left: 1px solid #000; vertical-align:top"'
        trashhtml += '<td valigh="top" align="center" {}>{}</td>\n'.format(
            style,
            "\n".join(discarded[c]),
        )
    trashhtml += "</tr></table><br/>"
    if foundtrash:
        trashhtml += 'Cards written in <font color="red">red</font> have been discarded or misplayed since your last turn.'

    trash = [trashhtml]  # ["<br/>".join(map(format_trash, localtrash))]
    hints = game.hints
    if hints == 0:
        hints = '<div style="font-weight: bold; font-size: 20pt">0</div>'
    mistakes = 3 - game.hits
    if mistakes == 2:
        mistakes = '<div style="font-weight: bold; font-size: 20pt; color: red">2</div>'
    cardsleft = len(game.deck)
    if cardsleft < 5:
        cardsleft = (
            '<div style="font-weight: bold; font-size: 20pt">%d</div>' % cardsleft
        )
    replaycontrol = ""
    if replay:
        (gid, round, info) = replay
        replaycontrol = "<br/><br/><br/><br/>"
        if not foundtrash:
            replaycontrol += "<br/><br/><br/>"
        replaycontrol += '<table style="font-size:14pt" width="100%" border="1">'
        replaycontrol += '<tr><td colspan="3">Replay of game ' + gid + "</td></tr>\n"
        replaycontrol += '<tr><td width="33%">'
        if round > 2:
            replaycontrol += '<a href="/replay/%s/%d">&lt;&lt;&lt;</a>' % (
                gid,
                round - 2,
            )
        else:
            replaycontrol += "&lt;&lt;&lt;"
        replaycontrol += '</td><td width="33%" align="center">'
        replaycontrol += " Turn " + str(round)
        replaycontrol += '</td><td width="33%" align="right">'
        if game.done():
            replaycontrol += "&gt;&gt;&gt;"
        else:
            replaycontrol += '<a href="/replay/%s/%d">&gt;&gt;&gt;</a>' % (
                gid,
                round + 2,
            )
        replaycontrol += "</td></tr>"
        ai, deck, score = info

        replaycontrol += (
            '<tr><td colspan="3" align="center">%s AI, %s, deck %d</td></tr>'
            % (ai, format_score(score), deck)
        )
        root = get_replay_root("log/game%s.log" % gid)
        if root == gid:
            replaycontrol += (
                '<tr><td colspan="3" align="center"><a href="/showsurvey/%s/full" target="_blank">Show survey answers</a></td></tr>'
                % root
            )
        else:
            replaycontrol += (
                '<tr><td colspan="3" align="center"><a href="/showsurvey/%s" target="_blank">Show survey answers</a></td></tr>'
                % root
            )
        replaycontrol += "</table>"
    args = tuple(
        [str(hints), str(mistakes), str(cardsleft)]
        + trash
        + [replaycontrol]
        + aicards
        + [board]
        + yourcards
        + [
            "\n".join(
                map(
                    lambda x: format_action(x, gid, replay),
                    enumerate(list(reversed(player.actions))[:15]),
                )
            )
        ]
    )
    return template % args


def make_circle(x, y, col):
    x += random.randint(-5, 5)
    y += random.randint(-5, 5)
    r0 = random.randint(0, 180)
    r1 = r0 + 360
    result = """
    <circle cx="%f" cy="%d" r="10" stroke="%s" stroke-width="4" fill="none">
       <animate attributeName="r" from="1" to="22" dur="2s" repeatCount="indefinite"/>
       <animate attributeName="stroke-dasharray" values="32, 32; 16, 16; 8,8; 4,4; 2,6; 1,7;" dur="2s" repeatCount="indefinite" calcMode="discrete"/>
       <animateTransform attributeName="transform" attributeType="XML" type="rotate" from="%f %f %f" to="%f %f %f" dur="2s" begin="0s" repeatCount="indefinite"/>
    </circle>
    """
    return result % (x, y, col, r0, x, y, r1, x, y)


def make_card_image(x, links=None, highlight=False):
    if links is None:
        links = []
    (col, num) = x
    image = """
<svg version="1.1" width="125" height="160" xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink">
    <rect width="125" height="160" x="0" y="0" fill="#66ccff"%s/>
    <text x="8" y="24" fill="%s" font-family="Arial" font-size="24" stroke="black">%s</text>
    <text x="50" y="24" fill="%s" font-family="Arial" font-size="24" stroke="black">%s</text>
    %s
    %s
    <text x="108" y="155" fill="%s" font-family="Arial" font-size="24" stroke="black">%s</text>
</svg>
"""
    ly = 130
    linktext = ""
    for text, target in links:
        linktext += """<a xlink:href="%s">
                           <text x="8" y="%d" fill="blue" font-family="Arial" font-size="12" text-decoration="underline">%s</text>
                       </a>
                       """ % (target, ly, text)
        ly += 23
    left = 35  # left
    right = 90  # right
    center_h = 62  # center (horizontal)

    top = 45  # top
    middle_v = 70  # middle (vertical)
    bottom = 95  # bottom
    circles = {
        0: [],
        1: [(center_h, middle_v)],
        2: [(left, top), (right, bottom)],
        3: [(left, bottom), (right, bottom), (center_h, top)],
        4: [(left, bottom), (right, bottom), (left, top), (right, top)],
        5: [
            (left, bottom),
            (right, bottom),
            (left, top),
            (right, top),
            (center_h, middle_v),
        ],
    }
    circ = "\n".join(
        map(lambda x: make_circle(x[0], x[1], col.display_name), circles[num])
    )
    highlighttext = ""
    if highlight:
        highlighttext = ' stroke="red" stroke-width="4"'
    return image % (
        highlighttext,
        col.display_name,
        str(num),
        col.display_name,
        col.display_name,
        circ,
        linktext,
        col.display_name,
        str(num),
    )


def unknown_card_image(links=None, highlight=False):
    if links is None:
        links = []
    image = """
<svg version="1.1" width="125" height="160" xmlns="http://www.w3.org/2000/svg">
    <rect width="125" height="160" x="0" y="0" fill="#66ccff"%s/>
    %s
    <text x="35" y="90" fill="black" font-family="Arial" font-size="100">?</text>
</svg>
"""
    ly = 130
    linktext = ""
    for text, target in links:
        linktext += """<a xlink:href="%s">
                           <text x="8" y="%d" fill="blue" font-family="Arial" font-size="12" text-decoration="underline">%s</text>
                       </a>
                       """ % (target, ly, text)
        ly += 23
    highlighttext = ""
    if highlight:
        highlighttext = ' stroke="red" stroke-width="4"'
    return image % (highlighttext, linktext)


gameslock = threading.Lock()
games = {}
participantslock = threading.Lock()
participants = {}
participantstarts = {}


class HTTPPlayer(Player):
    def __init__(self, name, pnr):
        super().__init__(name, pnr)
        self.actions = []
        self.knows = [set() for _ in range(5)]
        self.aiknows = [set() for _ in range(5)]
        self.show = []

    @override
    def reset(self) -> None:
        self.actions = []
        self.knows = [set() for _ in range(5)]
        self.aiknows = [set() for _ in range(5)]
        self.show = []

    def inform(self, action, player, game):
        if player == 1:
            self.show = []
        card = None
        if action.action_type in [
            Action.ActionType.PLAY,
            Action.ActionType.DISCARD,
        ]:
            card = game.hands[player][action.cnr]
        self.actions.append((action, player, card))
        if player != self.pnr:
            if action.action_type == Action.ActionType.HINT_COLOR:
                for i, (col, num) in enumerate(game.hands[self.pnr]):
                    if col == action.col:
                        self.knows[i].add(col.display_name)
                        self.show.append((HAND, self.pnr, i))
            elif action.action_type == Action.ActionType.HINT_NUMBER:
                for i, (col, num) in enumerate(game.hands[self.pnr]):
                    if num == action.num:
                        self.knows[i].add(str(num))
                        self.show.append((HAND, self.pnr, i))
        else:
            if action.action_type == Action.ActionType.HINT_COLOR:
                for i, (col, num) in enumerate(game.hands[action.pnr]):
                    if col == action.col:
                        self.aiknows[i].add(col.display_name)
                        self.show.append((HAND, action.pnr, i))
            elif action.action_type == Action.ActionType.HINT_NUMBER:
                for i, (col, num) in enumerate(game.hands[action.pnr]):
                    if num == action.num:
                        self.aiknows[i].add(str(num))
                        self.show.append((HAND, action.pnr, i))

        if (
            action.action_type in [Action.ActionType.PLAY, Action.ActionType.DISCARD]
            and player == 0
        ):
            newshow = []
            for where, who, what in self.show:
                if who == 0 and where == HAND:
                    if what < action.cnr:
                        newshow.append((where, who, what))
                    elif what > action.cnr:
                        newshow.append((where, who, what - 1))
                else:
                    newshow.append((where, who, what))
            self.show = newshow
        if action.action_type == Action.ActionType.DISCARD:
            newshow = []
            for t, w1, w2 in self.show:
                if t == TRASH:
                    newshow.append((t, w1, w2 - 1))
                else:
                    newshow.append((t, w1, w2))
            self.show = newshow
            self.show.append((TRASH, 0, -1))

        elif action.action_type == Action.ActionType.PLAY:
            (col, num) = game.hands[player][action.cnr]
            if game.board[col][1] + 1 == num:
                self.show.append((BOARD, 0, col))
            else:
                newshow = []
                for t, w1, w2 in self.show:
                    if t == TRASH:
                        newshow.append((t, w1, w2 - 1))
                    else:
                        newshow.append((t, w1, w2))
                self.show = newshow
                self.show.append((TRASH, 0, -1))
        if player == self.pnr and action.action_type in [
            Action.ActionType.PLAY,
            Action.ActionType.DISCARD,
        ]:
            del self.knows[action.cnr]
            self.knows.append(set())
        if player != self.pnr and action.action_type in [
            Action.ActionType.PLAY,
            Action.ActionType.DISCARD,
        ]:
            del self.aiknows[action.cnr]
            self.aiknows.append(set())


class ReplayHTTPPlayer(HTTPPlayer):
    def __init__(self, name, pnr):
        super().__init__(name, pnr)
        self.actions = []

    @override
    def reset(self) -> None:
        self.actions = []

    def get_action(
        self, nr, hands, knowledge, trash, played, board, valid_actions, hints
    ):
        return self.actions.pop(0)


class ReplayPlayer(Player):
    def __init__(self, name, pnr):
        super().__init__(name, pnr)
        self.actions = []
        self.realplayer = None

    @override
    def reset(self) -> None:
        self.actions = []

    def get_action(
        self, nr, hands, knowledge, trash, played, board, valid_actions, hints
    ):
        if self.realplayer:
            self.realplayer.get_action(
                nr, hands, knowledge, trash, played, board, valid_actions, hints
            )
        return self.actions.pop(0)

    def inform(self, action, player, game):
        if self.realplayer:
            self.realplayer.inform(action, player, game)

    def get_explanation(self):
        if self.realplayer:
            return self.realplayer.get_explanation()
        return []


def get_replay_info(fname):
    f = open(fname)
    ai = None
    deck = None
    score = None
    try:
        for line in f:
            if line.startswith("Treatment:"):
                try:
                    items = line.strip().split()
                    ai = items[-2].strip("'(,")
                    deck = int(items[-1].strip(")"))
                except Exception:
                    deck = None
            elif line.startswith("Score"):
                items = line.strip().split()
                score = int(items[1])
    except Exception:
        f.close()
        return (None, None, None)
    f.close()

    return (ai, deck, score)


def get_replay_root(fname):
    f = open(fname)
    parent = None
    for line in f:
        if line.startswith("Old GID:"):
            parent = line[8:].strip()
            break
    f.close()
    if parent:
        return get_replay_root("log/game%s.log" % parent)
    return fname[8:24]


def format_score(sc):
    if sc is None:
        return "not finished"
    return "%d points" % sc


# AIClasses
ais = {
    "random": Player,
    "inner": InnerStatePlayer,
    "outer": OuterStatePlayer,
    "self": SelfRecognitionPlayer,
    "intentional": IntentionalPlayer,
    "full": SelfIntentionalPlayer,
    "full-with-mem": SelfIntentionalPlayerWithMemory,
    "full-detect-dead": SelfIntentionalPlayerDetectDeadColors,
}


class MyHandler(BaseHTTPRequestHandler):
    def do_HEAD(s):
        s.send_response(200)
        s.send_header("Content-type", "text/html")
        s.end_headers()

    def do_GET(s):
        try:
            return s.perform_response()
        except Exception:
            errlog.write(traceback.format_exc())
            errlog.flush()

    def invalid(s, gid):
        if len(gid) != 16:
            return True
        for c in gid:
            if c not in "0123456789abcdef":
                return True
        if not os.path.exists("log/game%s.log" % gid):
            return True
        return False

    def perform_response(s):
        """Respond to a GET request."""
        global games

        game = None
        player = None
        turn = None
        gid = None
        path = s.path
        if s.path.startswith("/gid"):
            gid = s.path[4:20]
            gameslock.acquire()
            if gid in games:
                game, player, turn = games[gid]
            gameslock.release()
            path = s.path[20:]

        if s.path == "/hanabiui.png":
            f = open("hanabiui.png", "rb")
            s.send_response(200)
            s.send_header("Content-type", "image/png")
            s.end_headers()
            shutil.copyfileobj(f, s.wfile)
            f.close()
            return

        if s.path.startswith("/favicon"):
            s.send_response(200)
            s.end_headers()
            return

        # I honestly don't know why, but I already received a request for http://www.google.com
        if s.path.startswith("http://"):
            s.send_response(400)
            s.end_headers()
            return

        if s.path.startswith("/robots.txt"):
            s.send_response(200)
            s.send_header("Content-type", "text/plain")
            s.end_headers()
            s.wfile.write(b"User-agent: *\n")
            s.wfile.write(b"Disallow: /\n")
            return

        s.send_response(200)
        s.send_header("Content-type", "text/html")
        s.end_headers()

        if path.startswith("/tutorial"):
            gid = s.getgid()
            todelete = []
            participantslock.acquire()
            try:
                for g in participantstarts:
                    if participantstarts[g] + 7200 < time.time():
                        todelete.append(g)
                for d in todelete:
                    del participants[d]
                    del participantstarts[d]
            except Exception:
                import traceback

                errlog.write("Error cleaning participants:\n")
                errlog.write(traceback.format_exc())
            participants[gid] = open("log/survey%s.log" % gid, "w")
            participantstarts[gid] = time.time()
            participantslock.release()
            s.wfile.write(b"<html><head><title>Hanabi</title></head>")
            s.wfile.write(b"<body><center>")
            s.wfile.write(tutorial.intro.encode())
            if not path.startswith("/tutorial/newtab"):
                s.wfile.write(
                    b'<br/>If you want to open this tutorial in a new tab for reference during the game, click here  <a href="/tutorial/newtab" target="_blank">here</a><br/>\n'
                )
                s.wfile.write(
                    f'<form action="/tutorialdone" method="POST"><input type="hidden" value="{gid}" name="gid"/><input type="submit" value="Continue"/></form>\n'.encode()
                )

            s.wfile.write(tutorial.summary.encode())

            s.wfile.write(b"</center></body></html>")
            return

        if s.path.startswith("/postsurvey/"):
            gid = s.path[12:]
            if gid in participants:
                s.postsurvey(gid)
            return

        if s.path.startswith("/consent"):
            s.consentform()
            return
        replay = False
        if path.startswith("/new/study/"):
            oldgid = path[11:]
            if s.invalid(oldgid):
                s.wfile.write(b"<html><head><title>Hanabi</title></head>\n")
                s.wfile.write(b"<body><h1>Invalid Game ID</h1>\n")
                s.wfile.write(b"</body></html>")
                return

            gid = s.getgid()

            treatments = [
                ("intentional", 1),
                ("intentional", 2),
                ("intentional", 3),
                ("intentional", 4),
                ("intentional", 5),
                ("outer", 1),
                ("outer", 2),
                ("outer", 3),
                ("outer", 4),
                ("outer", 5),
                ("full", 1),
                ("full", 2),
                ("full", 3),
                ("full", 4),
                ("full", 5),
            ]
            random.seed(None)
            t = random.choice(treatments)
            nr = random.randint(6, 10000)
            type = t[0]
            t = (type, nr)
            if type in ais:
                ai = ais[type](type, 0)
            turn = 1
            player = HTTPPlayer("You", 1)
            log = open("log/game%s.log" % gid, "w")
            print("Old GID:", oldgid, file=log)
            print("Treatment:", t, file=log)
            random.seed(nr)
            game = Game([ai, player], log=log, format=1)
            game.treatment = t
            game.ping = time.time()
            game.started = False
            game.study = True
            todelete = []
            gameslock.acquire()
            for g in games:
                if games[g][0].ping + 3600 < time.time():
                    todelete.append(g)
            for g in todelete:
                del games[g]
            games[gid] = (game, player, turn)
            gameslock.release()

        elif path.startswith("/new/") and debug:
            type = s.path[5:]
            if type in ais:
                ai = ais[type](type, 0)
            turn = 1
            player = HTTPPlayer("You", 1)
            nr = random.randint(6, 10000)
            t = (type, nr)
            gid = s.getgid()
            log = open("log/game%s.log" % gid, "w")
            print("Treatment:", t, file=log)
            game = Game([ai, player], log=log, format=1)
            game.treatment = t
            game.ping = time.time()
            game.started = False
            todelete = []
            gameslock.acquire()
            for g in games:
                if games[g][0].ping + 3600 < time.time():
                    todelete.append(g)
            for g in todelete:
                del games[g]
            games[gid] = (game, player, turn)
            gameslock.release()

        elif path.startswith("/replay/") and debug:
            gid = path[8:24]
            rest = path[25:]

            items = rest.split("/")
            round = items[0]
            if len(items) > 1 and items[1] == "explain":
                path = "/explain"

            fname = "log/game%s.log" % gid
            try:
                round = int(round)
            except Exception:
                import traceback

                traceback.print_exc()
                round = None
            if "/" in gid or "\\" in gid or round is None or not os.path.exists(fname):
                s.wfile.write(b"<html><head><title>Hanabi</title></head>\n")
                s.wfile.write(b"<body><h1>Invalid Game ID</h1>\n")
                s.wfile.write(b"</body></html>")
                return

            info = get_replay_info(fname)

            replay = (gid, round, info)
            f = open(fname)
            players = [ReplayPlayer("AI", 0), ReplayHTTPPlayer("You", 1)]
            i = 0

            def convert(s):
                if s == "None":
                    return None
                return int(s)

            for line in f:
                if line.startswith("Treatment:"):
                    try:
                        items = line.strip().split()
                        ai = items[-2].strip("'(,")
                        players[0].realplayer = ais[ai](ai, 0)
                        deck = int(items[-1].strip(")"))

                    except Exception:
                        deck = None
                elif line.startswith("MOVE:"):
                    items = map(lambda s: s.strip(), line.strip().split())
                    const, pnum, type, cnr, pnr, col, num = items
                    a = Action(
                        Action.ActionType(convert(type)),
                        convert(pnr),
                        convert(col),
                        convert(num),
                        convert(cnr),
                    )
                    players[int(pnum)].actions.append(a)
                    i += 1
                if i >= round:
                    break
            if not deck:
                s.wfile.write(b"<html><head><title>Hanabi</title></head>\n")
                s.wfile.write(b"<body><h1>Invalid Game Log</h1>\n")
                s.wfile.write(b"</body></html>")
                return
            player = players[1]
            random.seed(deck)
            game = Game(players, log=NullStream())
            game.started = time.time()
            for i in range(round):
                game.single_turn()
            turn = -1
            gid = ""
        elif path.startswith("/starttakeover/"):
            items = list(filter(None, path.split("/")))
            if len(items) < 6:
                s.wfile.write(b"<html><head><title>Hanabi</title></head>\n")
                s.wfile.write(b"<body><h1>Invalid Game ID</h1>\n")
                s.wfile.write(b"</body></html>")
                return
            gid, round, ai, action, arg = items[1:]
            oldgid = gid
            fname = "log/game%s.log" % gid
            try:
                round = int(round)
            except Exception:
                import traceback

                traceback.print_exc()
                round = None
            if "/" in gid or "\\" in gid or round is None or not os.path.exists(fname):
                s.wfile.write(b"<html><head><title>Hanabi</title></head>\n")
                s.wfile.write(b"<body><h1>Invalid Game ID</h1>\n")
                s.wfile.write(b"</body></html>")
                return

            info = get_replay_info(fname)
            f = open(fname)
            players = [ReplayPlayer(ai.capitalize(), 0), ReplayHTTPPlayer("You", 1)]
            players[0].realplayer = ais[ai](ai.capitalize(), 0)
            i = 0

            def convert(s):
                if s == "None":
                    return None
                return int(s)

            for line in f:
                if line.startswith("Treatment:"):
                    try:
                        items = line.strip().split()
                        deck = int(items[-1].strip(")"))
                    except Exception:
                        deck = None
                elif line.startswith("MOVE:"):
                    items = map(lambda s: s.strip(), line.strip().split())
                    const, pnum, type, cnr, pnr, col, num = items
                    a = Action(
                        Action.ActionType(convert(type)),
                        convert(pnr),
                        convert(col),
                        convert(num),
                        convert(cnr),
                    )
                    players[int(pnum)].actions.append(a)
                    i += 1
                if i >= round:
                    break
            if not deck:
                s.wfile.write(b"<html><head><title>Hanabi</title></head>\n")
                s.wfile.write(b"<body><h1>Invalid Game Log</h1>\n")
                s.wfile.write(b"</body></html>")
                return
            player = players[1]
            random.seed(deck)
            gid = s.getgid()
            t = (ai, deck)
            log = open("log/game%s.log" % gid, "w")
            print("Original:", oldgid, file=log)
            print("Treatment:", t, file=log)
            game = Game(players, log=log, format=1)
            game.treatment = t
            game.ping = time.time()
            game.started = True
            for i in range(round):
                game.single_turn()
            game.players[0] = game.players[0].realplayer
            game.current_player = 1
            turn = round + 1
            gameslock.acquire()
            games[gid] = (game, players[1], turn)
            gameslock.release()
            path = "/%d/%s/%s" % (turn, action, arg)

        elif path.startswith("/showsurvey/"):
            gid = path[12:28]
            fname = "log/survey%s.log" % gid

            if "/" in gid or "\\" in gid or not os.path.exists(fname):
                s.wfile.write(b"<html><head><title>Hanabi</title></head>\n")
                s.wfile.write(
                    b"<body><h1>No survey answers recorded for this game ID</h1>\n"
                )
                s.wfile.write(b"</body></html>")
                return
            f = open(fname)
            answers = {}
            for line in f:
                if line.strip():
                    q, a = line.split(None, 1)
                    answers[q.strip()] = a.strip()
            f.close()
            s.wfile.write(b"<html><head><title>Hanabi</title></head>\n")
            s.wfile.write(b"<body><h1>Survey responses for %s</h1>\n" % gid)
            s.presurvey_questions(answers)
            if path.endswith("full"):
                s.postsurvey_questions(answers)

            s.wfile.write(b"</body></html>")
            return
        elif path.startswith("/selectreplay/"):
            filters = path[14:].split("/")
            filters = dict(zip(filters[::2], filters[1::2]))
            s.wfile.write(b"<html><head><title>Hanabi</title></head>\n")
            s.wfile.write(b"<body>")
            s.wfile.write(b"<h1>Replay selection</h1>")
            s.wfile.write(b"<h2>Filters:</h2>")

            def format_filters(f):
                result = ""
                for k in f:
                    result += "{}/{}/".format(k, f[k])
                return result

            def update_filters(f, k, v):
                result = dict(f)
                if v:
                    result[k] = v
                elif k in result:
                    del result[k]
                return result

            s.wfile.write(b"<p>AI: ")

            for i, (display, value) in enumerate(
                [
                    ("Outer State AI", "outer"),
                    ("Intentional AI", "intentional"),
                    ("Full AI", "full"),
                ]
            ):
                s.wfile.write(
                    f' <a href="/selectreplay/{format_filters(update_filters(filters, "ai", value))}">{display}</a> - '.encode()
                )
            s.wfile.write(
                f' <a href="/selectreplay/{format_filters(update_filters(filters, "ai", ""))}">any</a></p>'.encode()
            )

            s.wfile.write(b"<p>Score: ")

            for i, (display, value) in enumerate(
                [
                    ("0-4", "0"),
                    ("5-9", "1"),
                    ("10-14", "2"),
                    ("15-19", "3"),
                    ("20-24", "4"),
                    ("25", "5"),
                ]
            ):
                s.wfile.write(
                    f' <a href="/selectreplay/{format_filters(update_filters(filters, "score", value))}">{display}</a> - '.encode()
                )
            s.wfile.write(
                f' <a href="/selectreplay/{format_filters(update_filters(filters, "score", ""))}">any</a></p>'.encode()
            )

            s.wfile.write(b"<p>Deck: ")

            for i, (display, value) in enumerate(
                [
                    ("1", "1"),
                    ("2", "2"),
                    ("3", "3"),
                    ("4", "4"),
                    ("5", "5"),
                    ("other", "other"),
                ]
            ):
                s.wfile.write(
                    f' <a href="/selectreplay/{format_filters(update_filters(filters, "deck", value))}">{display}</a> - '.encode()
                )
            s.wfile.write(
                f' <a href="/selectreplay/{format_filters(update_filters(filters, "deck", ""))}">any</a></p>'.encode()
            )

            s.wfile.write(b"Select a replay to view:<br/><ul>")
            replays = []

            def match(filters, ai, deck, score):
                if "ai" in filters and ai != filters["ai"]:
                    return False
                if "score" in filters and (
                    score is None or score // 5 != int(filters["score"])
                ):
                    return False
                if "deck" in filters and (
                    (str(deck) != filters["deck"] and filters["deck"] != "other")
                    or (filters["deck"] == "other" and deck <= 5)
                ):
                    return False

                return True

            for f in os.listdir("log/"):
                if f.startswith("game"):
                    gid = f[4:20]
                    fname = os.path.join("log", f)
                    (ai, deck, score) = get_replay_info(fname)
                    if ai and deck and match(filters, ai, deck, score):
                        entry = (
                            '<li><a href="/replay/%s/1">Game %s (%s AI, %s, deck %d)</a></li>\n'
                            % (gid, gid, ai, format_score(score), deck)
                        )
                        replays.append(((score if score else -1), entry))
            replays.sort(key=lambda x: -x[0])
            for score, entry in replays:
                s.wfile.write(entry.encode())
            return
        elif path.startswith("/takeover/"):
            items = list(filter(None, path.split("/")))

            if len(items) < 5:
                s.wfile.write(b"<html><head><title>Hanabi</title></head>\n")
                s.wfile.write(b"<body><h1>Invalid Game ID</h1>\n")
                s.wfile.write(b"</body></html>")
                return
            gid, round, action, arg = items[1:]
            fname = "log/game%s.log" % gid
            try:
                round = int(round)
            except Exception:
                import traceback

                traceback.print_exc()
                round = None
            if "/" in gid or "\\" in gid or round is None or not os.path.exists(fname):
                s.wfile.write(b"<html><head><title>Hanabi</title></head>\n")
                s.wfile.write(b"<body><h1>Invalid Game ID</h1>\n")
                s.wfile.write(b"</body></html>")
                return
            (ai, deck, score) = get_replay_info(fname)
            s.wfile.write(b"<html><head><title>Hanabi</title></head>\n")
            s.wfile.write(b"<body><h1>Take over game</h1>\n")
            s.wfile.write(
                b"<p>If you continue, you will take over playing the game you were viewing from turn %d onward</p>"
                % round
            )
            s.wfile.write(
                f'<p>You may choose to use the same AI as the player that was playing the game by clicking <a href="/starttakeover/{gid}/{round + 1}/{ai}/{action}/{arg}">here</a></p>\n'.encode()
            )
            s.wfile.write(b"<p>You may also choose any AI to play with:</p><ul>")
            for a in ais:
                s.wfile.write(
                    f'<li><a href="/starttakeover/{gid}/{round + 1}/{a}/{action}/{arg}">{a.capitalize()} AI</a></li>'.encode()
                )

            s.wfile.write(b"</ul></p></body></html>")
            return

        if gid is None or game is None or path.startswith("/restart/"):
            if not debug:
                s.wfile.write(b"<html><head><title>Hanabi</title></head>\n")
                s.wfile.write(b"<body><h1>Invalid Game ID</h1>\n")
                s.wfile.write(b"</body></html>")
                return
            if game is not None:
                del game
            gameslock.acquire()
            if gid is not None and gid in games:
                del games[gid]
            gameslock.release()
            # AIList
            # /new/<foo> will look up <foo> in the ais dictionary, so make sure the names match
            s.wfile.write(b"<html><head><title>Hanabi</title></head>\n")
            s.wfile.write(
                b"<body><h1>Welcome to Hanabi</h1> <p>To start, choose an AI:</p>\n"
            )
            s.wfile.write(b'<ul><li><a href="/new/random">Random</a></li>\n')
            s.wfile.write(b'<li><a href="/new/inner">Inner State</a></li>\n')
            s.wfile.write(b'<li><a href="/new/outer">Outer State</a></li>\n')
            s.wfile.write(b'<li><a href="/new/self">Self Recognition</a></li>\n')
            s.wfile.write(
                b'<li><a href="/new/intentional">Intentional Player</a></li>\n'
            )
            s.wfile.write(
                b'<li><a href="/new/full">Fully Intentional Player</a></li>\n'
            )
            s.wfile.write(
                b'<li><a href="/new/full-with-mem">Fully Intentional Player with Memory</a></li>\n'
            )
            s.wfile.write(
                b'<li><a href="/new/full-detect-dead">Fully Intentional Player with Dead Color Detection</a></li>\n'
            )
            s.wfile.write(b"</ul><br/>")
            s.wfile.write(
                b'<p>Or select a <a href="/selectreplay/">replay file to view</a></p>'
            )
            s.wfile.write(b"</body></html>")
            return

        if path.startswith("/explain") and debug:
            s.show_explanation(game)
            return

        if path.startswith("/start/"):
            game.single_turn()
            game.started = True

        parts = path.strip("/").split("/")
        if parts[0] == str(turn):
            actionname = parts[1]
            index = int(parts[2])
            action = None
            if actionname == "hintcolor" and game.hints > 0:
                col = game.hands[0][index][0]
                action = Action(Action.ActionType.HINT_COLOR, pnr=0, col=col)
            elif actionname == "hintrank" and game.hints > 0:
                nr = game.hands[0][index][1]
                action = Action(Action.ActionType.HINT_NUMBER, pnr=0, num=nr)
            elif actionname == "play":
                action = Action(Action.ActionType.PLAY, pnr=1, cnr=index)
            elif actionname == "discard":
                action = Action(Action.ActionType.DISCARD, pnr=1, cnr=index)

            if action:
                turn += 1
                gameslock.acquire()
                games[gid] = (game, player, turn)
                gameslock.release()
                game.external_turn(action)
                game.single_turn()

        s.wfile.write(b"<html><head><title>Hanabi</title></head>")
        s.wfile.write(b"<body>")

        s.wfile.write(show_game_state(game, player, turn, gid, replay).encode())

        s.wfile.write(b"</body></html>")
        if game.done() and gid is not None and gid in games:
            errlog.write(
                "%s game done. Score: %d\n" % (str(game.treatment), game.score())
            )
            errlog.flush()
            game.finish()
            del [gid]

    def show_explanation(s, game):
        s.wfile.write(b"<html><head><title>Hanabi - AI Explanation</title></head>")
        s.wfile.write(b"<body>")

        s.wfile.write(b'<table border="1">')
        s.wfile.write(
            b"<tr><th>Description</th><th>Card 1</th><th>Card 2</th><th>Card 3</th><th>Card 4</th><th>Card 5</th>\n"
        )
        for line in game.players[0].get_explanation():
            s.wfile.write(b"<tr>\n")
            for item in line:
                s.wfile.write(
                    f"\t<td>{str(item).replace('\n', '<br/>')}</td>\n".encode()
                )
            s.wfile.write(b"</tr>\n")
        s.wfile.write(b"</table>\n")

        s.wfile.write(b"</body></html>")

    def add_choice(s, name, question, answers, default=-1):
        s.wfile.write(b"<p>")
        s.wfile.write((question + "<br/>").encode())
        s.wfile.write(f'<fieldset id="{name}">\n'.encode())
        for i, (aname, text) in enumerate(answers):
            if i == default:
                s.wfile.write(
                    f'<input name="{name}" type="radio" value="{aname}" id="{name}{aname}" checked="checked"/><label for="{name}{aname}">{text}</label><br/>\n'.encode()
                )
            else:
                s.wfile.write(
                    f'<input name="{name}" type="radio" value="{aname}" id="{name}{aname}"/><label for="{name}{aname}">{text}</label><br/>\n'.encode()
                )
        s.wfile.write(b"</fieldset>\n")
        s.wfile.write(b"</p>")

    def add_question(s, name, question):
        s.wfile.write(b"<p>")
        s.wfile.write((question + "<br/>").encode())
        s.wfile.write(f'<input name="{name}"/>\n'.encode())
        s.wfile.write(b"</p>")

    def presurvey(s, gid, warn=False):
        s.wfile.write(
            b"<center><h1>Finally, please answer some question about previous board game experience</h1>"
        )
        s.wfile.write(b'<table width="600px">\n<tr><td>')
        s.wfile.write(b'<form action="/submitpost2" method="POST">')
        s.presurvey_questions()
        s.wfile.write(b"<p>")
        s.wfile.write(f'<input name="gid" type="hidden" value="{gid}"/>\n'.encode())
        s.wfile.write(b'<input type="submit" value="Finish"/>\n')
        s.wfile.write(b"</form></td></tr></table></center>")

    def presurvey_questions(s, answers=None):
        if answers is None:
            answers = {}

        responses = [
            ("20s", "18-29 years"),
            ("30s", "30-39 years"),
            ("40s", "40-49 years"),
            ("50s", "50-64 years"),
            ("na", "Prefer not to answer"),
        ]
        default = -1
        if "age" in answers:
            default = list(list(map(lambda x: x[0], responses))).index(answers["age"])
        s.add_choice("age", "What is your age?", responses, default)

        responses = [
            ("new", "I never play board or card games"),
            ("dabbling", "I rarely play board or card games"),
            ("intermediate", "I sometimes play board or card games"),
            ("expert", "I often play board or card games"),
        ]
        default = -1
        if "bgg" in answers:
            default = list(list(map(lambda x: x[0], responses))).index(answers["bgg"])
        s.add_choice(
            "bgg",
            "How familiar are you with the board and card games in general?",
            responses,
            default,
        )

        responses = [("yes", "Yes"), ("no", "No")]
        default = -1
        if "gamer" in answers:
            default = list(list(map(lambda x: x[0], responses))).index(answers["gamer"])
        s.add_choice(
            "gamer",
            "Do you consider yourself to be a (board) gamer?",
            responses,
            default,
        )

        responses = [
            ("new", "I have never played before participating in this experiment"),
            ("dabbling", "I have played a few (1-10) times"),
            ("intermediate", "I have played multiple (10-50) times"),
            ("expert", "I have played many (&gt; 50) times"),
        ]
        default = -1
        if "exp" in answers:
            default = list(list(map(lambda x: x[0], responses))).index(answers["exp"])
        s.add_choice(
            "exp", "How familiar are you with the card game Hanabi?", responses, default
        )

        responses = [
            (
                "never",
                "I have never played before or can't remember when I played the last time",
            ),
            ("long", "The last time I played has been a long time (over a year) ago"),
            (
                "medium",
                "The last time I played has been some time (between 3 months and a year) ago",
            ),
            ("recent", "The last time I played was recent (up to 3 months ago)"),
        ]
        default = -1
        if "recent" in answers:
            default = list(list(map(lambda x: x[0], responses))).index(
                answers["recent"]
            )
        s.add_choice(
            "recent",
            "When was the last time that you played Hanabi before this experiment?",
            responses,
            default,
        )

        responses = [
            ("never", "I never reach the top score, or I have never played Hanabi"),
            (
                "few",
                "I almost never reach the top score (about one in 50 or more games)",
            ),
            ("sometimes", "I sometimes reach the top score (about one in 6-20 games)"),
            ("often", "I often reach the top score (about one in 5 or fewer games)"),
        ]
        default = -1
        if "score" in answers:
            default = list(list(map(lambda x: x[0], responses))).index(answers["score"])
        s.add_choice(
            "score",
            "How often do you typically reach the top score of 25 in Hanabi?",
            responses,
            default,
        )

        responses = [("yes", "Yes"), ("no", "No")]
        default = 0
        if "gamer" in answers:
            default = list(list(map(lambda x: x[0], responses))).index(
                answers["publish"]
            )
        s.add_choice(
            "publish",
            "For this study we have recorded your answers to this survey, as well as a log of actions that you performed in the game. We have <b>not</b> recorded your IP address or any other information that could be linked back to you. Do you agree that we make your answers to the survey and the game log publicly available for future research?",
            responses,
            default,
        )

    def postsurvey(s, gid, warn=False):
        s.wfile.write(
            b"<center><h1>Please answer some questions about your experience with the AI</h1>"
        )
        s.wfile.write(b'<table width="600px">\n<tr><td>')
        s.wfile.write(b'<form action="/submitpost" method="POST">')
        s.postsurvey_questions()
        s.wfile.write(b"<p>")
        s.wfile.write(f'<input name="gid" type="hidden" value="{gid}"/>\n'.encode())
        s.wfile.write(b'<input type="submit" value="Continue"/>\n')
        s.wfile.write(b"</form></td></tr></table></center>")

    def postsurvey_questions(s, answers=None):
        if answers is None:
            answers = {}
        responses = [
            ("1", "Never performed goal-directed actions"),
            ("2", "Rarely performed goal-directed actions"),
            ("3", "Sometimes performed goal-directed actions"),
            ("4", "Often performed goal-directed actions"),
            ("5", "Always performed goal-directed actions"),
        ]
        default = -1
        if "intention" in answers:
            default = list(list(map(lambda x: x[0], responses))).index(
                answers["intention"]
            )
        s.add_choice(
            "intention",
            "How intentional/goal-directed did you think this AI was playing?",
            responses,
            default,
        )

        responses = [
            ("vbad", "The AI played very badly"),
            ("bad", "The AI played badly"),
            ("ok", "The AI played ok"),
            ("good", "The AI played well"),
            ("vgood", "The AI played very well"),
        ]
        default = -1
        if "skill" in answers:
            default = list(map(lambda x: x[0], responses)).index(answers["skill"])
        s.add_choice(
            "skill", "How would you rate the play skill of this AI?", responses, default
        )

        responses = [
            ("vhate", "I really disliked playing with this AI"),
            ("hate", "I somewhat disliked playing with this AI"),
            ("neutral", "I neither liked nor disliked playing with this AI"),
            ("like", "I somewhat liked playing with this AI"),
            ("vlike", "I really liked playing with this AI"),
        ]
        default = -1
        if "like" in answers:
            default = list(map(lambda x: x[0], responses)).index(answers["like"])
        s.add_choice(
            "like", "How much did you enjoy playing with this AI?", responses, default
        )

    def parse_POST(self):
        ctype, pdict = parse_header(self.headers["content-type"])
        if ctype == "multipart/form-data":
            postvars = parse_multipart(self.rfile, pdict)
        elif ctype == "application/x-www-form-urlencoded":
            length = int(self.headers["content-length"])
            postvars = parse_qs(self.rfile.read(length), keep_blank_values=True)
        else:
            postvars = {}
        return postvars

    def getgid(s):
        peer = str(s.connection.getpeername()) + str(time.time()) + str(os.urandom(4))
        return hashlib.sha224(peer.encode()).hexdigest()[:16]

    def do_POST(s):
        s.send_response(200)
        s.send_header("Content-type", "text/html")
        s.end_headers()
        tvars = s.parse_POST()
        vars = {}
        for v in tvars:
            vars[v] = tvars[v][0]
        if s.path.startswith("/submitpost2"):
            required = ["score", "age", "recent", "exp", "bgg", "gamer", "publish"]

            gid = s.getgid()
            if "gid" in vars and vars["gid"]:
                gid = vars["gid"]

            if gid not in participants:
                print(gid, "not in participants", participants, file=errlog)
                return s.presurvey(gid)

            participantslock.acquire()
            for r in required:
                if r in vars:
                    print(r, vars[r], file=participants[gid])
            participants[gid].close()
            del participants[gid]
            del participantstarts[gid]
            participantslock.release()
            s.wfile.write(b"<html><head><title>Hanabi</title></head>")
            s.wfile.write(b"<body><center>")
            s.wfile.write(b"<h1>Thank you for your participation in this study!</h1>")

            s.wfile.write(
                b'<a href="/new/study/%s">Play again</a><br/>You can bookmark this link and play again at any later time. <br/>Any additional games you play will also be recorded for future analysis, and published if you agreed to publication.'
                % (gid)
            )

            s.wfile.write(b"</body></html>")

        elif s.path.startswith("/tutorialdone"):
            gid = s.getgid()
            if "gid" in vars and vars["gid"]:
                gid = vars["gid"]
            participantslock.acquire()
            if gid not in participants:
                participants[gid] = open("log/survey%s.log" % gid, "w")
                participantstarts[gid] = time.time()
            participantslock.release()
            treatments = [
                ("intentional", 1),
                ("intentional", 2),
                ("intentional", 3),
                ("intentional", 4),
                ("intentional", 5),
                ("outer", 1),
                ("outer", 2),
                ("outer", 3),
                ("outer", 4),
                ("outer", 5),
                ("full", 1),
                ("full", 2),
                ("full", 3),
                ("full", 4),
                ("full", 5),
            ]
            random.seed(None)
            t = random.choice(treatments)
            type = t[0]
            if type in ais:
                ai = ais[type](type, 0)
            turn = 1
            player = HTTPPlayer("You", 1)
            log = open("log/game%s.log" % gid, "w")
            print("Treatment:", t, file=log)
            random.seed(t[1])
            game = Game([ai, player], log=log, format=1)
            game.treatment = t
            game.ping = time.time()
            game.dopostsurvey = True
            game.started = False
            todelete = []
            gameslock.acquire()
            for g in games:
                if games[g][0].ping + 3600 < time.time():
                    todelete.append(g)
            for g in todelete:
                del games[g]
            games[gid] = (game, player, turn)
            gameslock.release()
            s.wfile.write(b"<html><head><title>Hanabi</title></head>")
            s.wfile.write(b"<body>")

            s.wfile.write(show_game_state(game, player, turn, gid).encode())

            s.wfile.write(b"</body></html>")
        elif s.path.startswith("/submitpost"):
            required = ["intention", "skill", "like"]

            gid = s.getgid()
            if "gid" in vars and vars["gid"]:
                gid = vars["gid"]

            if gid not in participants:
                s.wfile.write(b"<html><head><title>Hanabi</title></head>")
                s.wfile.write(b"<body><center>")
                s.wfile.write(
                    b"<h1>Session timed out. Thank you for your time and participation</h1>"
                )
                s.wfile.write(b"</body></html>")
                return
            participantslock.acquire()
            for r in required:
                if r in vars:
                    print(r, vars[r], file=participants[gid])
            participants[gid].flush()
            participantslock.release()
            s.presurvey(gid)

    def consentform(s):
        s.wfile.write(b"<html><head><title>Hanabi</title></head>\n")
        s.wfile.write(b"<body>\n")
        s.wfile.write(consent.consent.encode())
        s.wfile.write(
            b'<center><font size="12"><a href="/tutorial">By clicking here I agree to participate in the study</a></font></center><br/><br/><br/>'
        )
        s.wfile.write(b"</body></html>")


class ThreadingHTTPServer(socketserver.ThreadingMixIn, HTTPServer):
    def finish_request(self, request, client_address):
        request.settimeout(30)
        # "super" can not be used because BaseServer is not created from object
        HTTPServer.finish_request(self, request, client_address)


if __name__ == "__main__":
    server_class = ThreadingHTTPServer
    if not os.path.exists("log/"):
        os.makedirs("log")
    httpd = server_class((HOST_NAME, PORT_NUMBER), MyHandler)
    errlog.write(
        time.asctime() + " Server Starts - {}:{}\n".format(HOST_NAME, PORT_NUMBER)
    )
    errlog.flush()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    httpd.server_close()
    errlog.write(
        time.asctime() + " Server Stops - {}:{}\n".format(HOST_NAME, PORT_NUMBER)
    )
    errlog.flush()
