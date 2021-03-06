#!/usr/bin/env python

import urllib2
import re
import datetime
import json

__epoch__ = datetime.datetime(1970, 1, 1)
__days_lookahead__ = 60

class Game:

    def __init__(self, time, blue_player, blue_score, red_player, red_score):
        self.time = time
        self.blue_player = blue_player
        self.blue_score = blue_score
        self.red_player = red_player
        self.red_score = red_score

    def __str__(self):
        return self.__repr__()

    def __repr__(self):
        timestamp = int((self.time - __epoch__).total_seconds())
        return '{time} {red} v {blue}'.format(time=timestamp, red=self.red_player, blue=self.blue_player)


def games():
    r = re.compile(r'([^\s]+)\s+([0-9]+)\s+([^\s]+)\s+([0-9]+)\s+([0-9]+)')
    data = urllib2.urlopen('http://int.corefiling.com/~aks/football/ladder.txt')
    # data = open('ladder.txt')
    for line in data:
        m = r.match(line)
        if m:
            d = datetime.datetime.fromtimestamp(int(m.group(5)))
            yield Game(d, m.group(1).lower(), float(m.group(2)), m.group(3).lower(), float(m.group(4)))


class Ranking:

    def __init__(self, time, ranking):
        self.time = time
        self.ranking = ranking


class Player:

    def __init__(self, name):
        self.name = name
        self.elo = 0.0
        self.games = 0
        self.most_recent_game = None
        self.active = False
        self.rankings = []

    def game(self, delta, time):
        self.active = True
        self.elo += delta
        self.games += 1

    def update_ranking(self, ranking, time, inactivate=False):
        ranking_changed = self.rankings and self.rankings[-1] and self.rankings[-1].ranking != ranking
        if ranking_changed:
            # Extra data point for pretty lines up/down
            extra_time = time - datetime.timedelta(1)
            extra_ranking = self.rankings[-1].ranking
            popped = None
            while self.rankings and self.rankings[-1] and self.rankings[-1].time > extra_time and self.rankings[-1].ranking != ranking:
                popped = self.rankings.pop(-1)

            if popped:
                if not self.rankings or not self.rankings[-1]:
                    # Popped the last point
                    # First approximation: put it back
                    # TODO: Move the line back according to imagined projection back?
                    extra_time = popped.time
                    extra_ranking = popped.ranking
                else:
                    # There is a previous point, intersect lines
                    previous = self.rankings[-1]
                    interval = time - previous.time
                    extra_time = interval / 2 + previous.time
                    fraction = float(interval.total_seconds()) / 24 / 60 / 60 / 2
                    extra_ranking = fraction * (popped.ranking - previous.ranking) + previous.ranking

            self.rankings.append(Ranking(extra_time, extra_ranking))

        if ranking_changed or inactivate or not self.rankings or not self.rankings[-1]:
            self.rankings.append(Ranking(time, ranking))

        if inactivate:
            self.active = False
            self.rankings.append(None)

    def write_final_rank(self, time):
        if self.active and self.rankings[-1]:
            self.rankings.append(Ranking(time, self.rankings[-1].ranking))

    def __str__(self):
        return self.__repr__()

    def __repr__(self):
        return self.name


class Analysis:

    def __init__(self):
        self.players = {}
        self.games = []

    def get_player(self, name):
        if name in self.players:
            return self.players[name]
        else:
            player = self.players[name] = Player(name)
            return player

    def game_played(self, new_game):

        if '-' in new_game.blue_player or '-' in new_game.red_player:
            # Filter out pdw-right etc.
            return

        self.process_games(time = new_game.time)

        self.games.append(new_game)
        self.get_player(new_game.blue_player).most_recent_game = new_game.time
        self.get_player(new_game.red_player).most_recent_game = new_game.time

    def process_games(self, time=None, flush=False):
        game = None
        while self.games and (flush or (time - self.games[0].time).days >= __days_lookahead__):
            game = self.games.pop(0)
            blue = self.get_player(game.blue_player)
            red = self.get_player(game.red_player)

            predict = 1 / (1 + 10 ** ((red.elo - blue.elo) / 180))
            result = game.blue_score / (game.blue_score + game.red_score)
            delta = 25 * (result - predict)

            blue.game(delta, game.time)
            red.game(-delta, game.time)

            players_by_rank = sorted([p for p in self.players.values() if p.active], key=lambda x: x.elo, reverse=True)

            rank = 1
            for player in players_by_rank:
                inactivate = not flush and player.most_recent_game == game.time
                player.update_ranking(rank, game.time, inactivate=inactivate)
                rank += 1

        if flush:
            for player in self.players.values():
                player.write_final_rank(datetime.datetime.now())


class RankingsEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Player):
            return {'label': obj.name, 'data': obj.rankings}
        if isinstance(obj, Ranking):
            return [obj.time, obj.ranking]
        if isinstance(obj, datetime.datetime):
            return (obj - __epoch__).total_seconds() * 1000
        else:
            return super(FootballJsonEncoder, self).default(obj)


def main():
    analysis = Analysis()
    for game in games():
        analysis.game_played(game)

    analysis.process_games(flush = True)

    print("Content-type: application/json\n")
    print(RankingsEncoder().encode(analysis.players.values()))


if __name__ == '__main__':
    main()
