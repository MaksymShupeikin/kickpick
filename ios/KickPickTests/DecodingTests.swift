import SwiftUI
import XCTest
@testable import KickPick

final class DecodingTests: XCTestCase {
    private func decode<T: Decodable>(_ type: T.Type, _ json: String) throws -> T {
        try JSONDecoder.api.decode(T.self, from: Data(json.utf8))
    }

    private let matchJSON = """
    {"id": 1, "competition": {"slug": "premier-league", "name": "Premier League",
      "logo_url": "https://images.fotmob.com/image_resources/logo/leaguelogo/dark/47.png"},
     "season": "2026/2027", "round": "6", "kickoff": "2026-10-12T19:00:00Z", "status": "LIVE", "minute": "45+2'",
     "home": {"id": 8669, "name": "Coventry City", "short_name": "Coventry",
              "logo_url": "https://images.fotmob.com/image_resources/logo/teamlogo/8669.png"},
     "away": {"id": 10261, "name": "Newcastle United", "short_name": "Newcastle", "logo_url": null},
     "home_score": 4, "away_score": 1
    """

    func testMatchDecodes() throws {
        let match = try decode(Match.self, matchJSON + "}")
        XCTAssertEqual(match.status, .live)
        XCTAssertEqual(match.minute, "45+2'")
        XCTAssertEqual(match.home.logoUrl?.lastPathComponent, "8669.png")
        XCTAssertEqual(match.kickoff, ISO8601DateFormatter().date(from: "2026-10-12T19:00:00Z"))
        XCTAssertEqual(match.weight(home: true), .even)  // still live: no winner yet
    }

    func testSpokenSummary() throws {
        let live = try decode(Match.self, matchJSON.replacingOccurrences(of: "45+2'", with: "67'") + "}")
        XCTAssertTrue(live.spokenSummary.contains("live, 67'"))
        let done = try decode(Match.self, matchJSON.replacingOccurrences(of: "LIVE", with: "FT") + "}")
        XCTAssertTrue(done.spokenSummary.hasSuffix("full time"))
    }

    func testMatchPageWithDetailsDecodes() throws {
        let page = try decode(MatchPage.self, matchJSON + """
        , "details": {"events": [{"minute": 90, "added": 5, "type": "goal", "side": "away", "player": "A",
          "assist": "B", "note": null, "score": "4-2"}], "stats": [{"name": "Ball possession", "home": "73", "away": "27"}]}}
        """)
        XCTAssertEqual(page.match.id, 1)
        XCTAssertEqual(page.details?.events.first?.minuteText, "90+5'")
        XCTAssertEqual(page.details?.stats.first?.homeValue, 73)
    }

    func testFractionalDatesDecode() throws {
        let match = try decode(Match.self, matchJSON.replacingOccurrences(of: "19:00:00Z", with: "19:00:00.000Z") + "}")
        XCTAssertEqual(match.kickoff, ISO8601DateFormatter().date(from: "2026-10-12T19:00:00Z"))
    }

    private let predictionJSON = """
    {"available": true, "experimental": true, "probabilities": {"home": 0.5, "draw": 0.3, "away": 0.2},
     "generated_at": "2026-10-11T19:00:00.123456+00:00", "model_version": "online-v1"}
    """

    func testPredictionDecodesOnlyForActiveMatches() throws {
        for status in ["NS", "LIVE", "FT", "CANC"] {
            let json = matchJSON.replacingOccurrences(of: "\"LIVE\"", with: "\"\(status)\"")
                + ", \"prediction\": \(predictionJSON)}"
            let page = try decode(MatchPage.self, json)
            if status == "NS" || status == "LIVE" {
                XCTAssertEqual(page.prediction?.probabilities.home, 0.5)
                XCTAssertEqual(page.prediction?.probabilities.draw, 0.3)
                XCTAssertEqual(page.prediction?.probabilities.away, 0.2)
                XCTAssertEqual(page.prediction?.probabilities.highest, 0.5)
            } else {
                XCTAssertNil(page.prediction)
            }
        }
    }

    func testMissingOrInvalidPredictionDoesNotBreakMatch() throws {
        XCTAssertNil(try decode(MatchPage.self, matchJSON + "}").prediction)
        for payload in ["null", #"{"available": false}"#,
                        predictionJSON.replacingOccurrences(of: "0.5", with: "-0.5"),
                        predictionJSON.replacingOccurrences(of: "0.5", with: "1.5"),
                        predictionJSON.replacingOccurrences(of: "0.5", with: "0.1"),
                        predictionJSON.replacingOccurrences(of: "0.5", with: "\"bad\""),
                        predictionJSON.replacingOccurrences(of: "2026-10-11T19:00:00.123456+00:00",
                                                           with: "2026-10-12T19:00:01Z")] {
            let page = try decode(MatchPage.self, matchJSON + ", \"prediction\": \(payload)}")
            XCTAssertEqual(page.match.id, 1)
            XCTAssertNil(page.prediction)
        }
    }

    func testMatchRefreshIntervalFollowsPredictionAndScoreLifecycle() throws {
        let cases: [(String, TimeInterval, Duration?)] = [
            ("NS", 86400, .seconds(600)), ("NS", 300, .seconds(15)),
            ("LIVE", -3600, .seconds(15)), ("FT", -3600, nil), ("CANC", 86400, nil)
        ]
        for (status, offset, interval) in cases {
            let kickoff = APIClient.isoUTC(.now.addingTimeInterval(offset))
            let json = matchJSON.replacingOccurrences(of: "2026-10-12T19:00:00Z", with: kickoff)
                .replacingOccurrences(of: "\"LIVE\"", with: "\"\(status)\"") + "}"
            XCTAssertEqual(try decode(MatchPage.self, json).refreshInterval, interval)
        }
    }

    func testBracketWithUnknownSide() throws {
        let bracket = try decode(Bracket.self, """
        {"rounds": [{"stage": "1/8", "matchups": [{"home": null,
          "away": {"id": 9847, "name": "PSG", "logo_url": "https://images.fotmob.com/image_resources/logo/teamlogo/9847.png"},
          "home_score": null, "away_score": null, "winner_id": null, "match_ids": []}]}], "third_place": null}
        """)
        XCTAssertNil(bracket.rounds[0].matchups[0].home)
        XCTAssertEqual(bracket.rounds[0].matchups[0].away?.name, "PSG")
    }

    func testSearchDecodes() throws {
        let results = try decode(SearchResults.self, """
        {"competitions": [{"slug": "champions-league", "name": "Champions League", "kind": "cup",
          "current_season": "2026/2027", "logo_url": null}],
         "teams": [{"id": 8634, "name": "Barcelona", "short_name": "Barcelona", "logo_url": null}],
         "players": [{"id": 1, "name": "Joan García", "photo_url": null, "team_name": "Barcelona"}],
         "matches": [\(matchJSON)}]}
        """)
        XCTAssertEqual(results.competitions[0].currentSeason, "2026/2027")
        XCTAssertEqual(results.players[0].teamName, "Barcelona")
        XCTAssertEqual(results.matches[0].home.name, "Coventry City")
        XCTAssertFalse(results.isEmpty)
        let onlyMatches = try decode(SearchResults.self, """
        {"competitions": [], "teams": [], "players": [], "matches": [\(matchJSON)}]}
        """)
        XCTAssertFalse(onlyMatches.isEmpty)
    }

    func testOldMatchDatesShowTheYear() throws {
        let old = try decode(Match.self, matchJSON.replacingOccurrences(of: "2026-10-12", with: "2022-12-18")
            .replacingOccurrences(of: "LIVE", with: "FT") + "}")
        XCTAssertEqual(old.statusLines(showDate: true), ["18 Dec", "2022"])  // two lines: no time for an old match
        XCTAssertEqual(old.statusLines(showDate: false).count, 1)  // the feed: the time alone
        let recent = try decode(Match.self, matchJSON.replacingOccurrences(of: "2026-10-12T19", with: ISO8601DateFormatter().string(from: .now).prefix(13))
            .replacingOccurrences(of: "LIVE", with: "FT") + "}")
        XCTAssertEqual(recent.statusLines(showDate: true).last, "Today")
        XCTAssertEqual(recent.statusLines(showDate: true).first?.count, 5)  // kick-off time, "21:00"
    }

    func testQueryDatesAreUTC() {
        let moscowMidnight = ISO8601DateFormatter().date(from: "2026-10-14T00:00:00+03:00")!
        XCTAssertEqual(APIClient.isoUTC(moscowMidnight), "2026-10-13T21:00:00Z")
    }

    func testRoundTitles() {
        XCTAssertEqual(roundTitle("7"), "Matchday 7")
        XCTAssertEqual(roundTitle("1/8"), "Round of 16")
        XCTAssertEqual(roundTitle("1/4"), "Quarter-finals")
        XCTAssertEqual(roundTitle("bronze"), "Third-place play-off")
        XCTAssertEqual(roundTitle("final"), "Final")
    }

    func testStatNumbers() {
        XCTAssertEqual(MatchStat.number("185 (70%)"), 185)
        XCTAssertEqual(MatchStat.number("1.47"), 1.47)
        XCTAssertEqual(MatchStat.number("—"), 0)
    }

    func testNeedsPolling() throws {
        func match(_ status: String, offset: TimeInterval) throws -> Match {
            let kickoff = ISO8601DateFormatter().string(from: Date.now.addingTimeInterval(offset))
            let json = matchJSON.replacingOccurrences(of: "2026-10-12T19:00:00Z", with: kickoff)
                .replacingOccurrences(of: "\"LIVE\"", with: "\"\(status)\"")
            return try decode(Match.self, json + "}")
        }
        XCTAssertTrue(try match("LIVE", offset: -3600).needsPolling)
        XCTAssertTrue(try match("NS", offset: 300).needsPolling)
        XCTAssertFalse(try match("NS", offset: 86400).needsPolling)
        XCTAssertFalse(try match("FT", offset: -3600).needsPolling)
    }

    func testZoneLegend() throws {
        let groups = try decode([StandingGroup].self, """
        [{"group": "A", "rows": [], "legend": [{"title": "Qualification next stage", "color": "#2AD572"}]},
         {"group": "B", "rows": [], "legend": [{"title": "Qualification next stage", "color": "#2AD572"},
                                              {"title": "Possible qualification next stage", "color": "#FFD908"}]},
         {"group": "C", "rows": []}]
        """)
        XCTAssertEqual(Zone.legend(of: groups).map(\.color), ["#2AD572", "#FFD908"])  // once each, in order
        XCTAssertNotNil(Color(hex: "#2AD572"))
        XCTAssertNil(Color(hex: "green"))
    }

    func testScorerLines() throws {
        let events = try decode([MatchEvent].self, """
        [{"minute": 23, "added": null, "type": "goal", "side": "home", "player": "Jack Hinshelwood", "assist": null,
          "note": null, "score": "1-0", "player_id": 1},
         {"minute": 45, "added": 2, "type": "goal", "side": "away", "player": "Mohamed Salah", "assist": null,
          "note": "Penalty", "score": "1-1", "player_id": 2},
         {"minute": 60, "added": null, "type": "yellow", "side": "home", "player": "A B", "assist": null,
          "note": null, "score": null, "player_id": null},
         {"minute": 67, "added": null, "type": "goal", "side": "home", "player": "Jack Hinshelwood", "assist": null,
          "note": null, "score": "2-1", "player_id": 1},
         {"minute": 82, "added": null, "type": "own_goal", "side": "home", "player": "Robert Sánchez", "assist": null,
          "note": null, "score": "3-1", "player_id": 3}]
        """)
        XCTAssertEqual(events.scorerLines(side: "home"), ["Hinshelwood 23', 67'", "Sánchez 82' (OG)"])
        XCTAssertEqual(events.scorerLines(side: "away"), ["Salah 45+2' (P)"])
    }

    func testRatingColours() {
        XCTAssertEqual(Color.rating(5.9), .loss)
        XCTAssertEqual(Color.rating(6.0), .cardYellow)
        XCTAssertEqual(Color.rating(6.99), .cardYellow)
        XCTAssertEqual(Color.rating(7.0), .win)
        XCTAssertEqual(Color.rating(8.0), .standout)
        XCTAssertEqual(Color.rating(9.6), .standout)
    }

    func testShortSeason() {
        XCTAssertEqual(CompetitionView.shortSeason("2026/2027"), "26/27")
        XCTAssertEqual(CompetitionView.shortSeason("2026/2027 - Apertura"), "26/27 Apertura")
        XCTAssertEqual(CompetitionView.shortSeason("2026"), "2026")
    }

    func testCurrentRound() throws {
        func match(_ round: String, _ status: String, days: Double) throws -> Match {
            let kickoff = ISO8601DateFormatter().string(from: Date.now.addingTimeInterval(days * 86400))
            let json = matchJSON.replacingOccurrences(of: "2026-10-12T19:00:00Z", with: kickoff)
                .replacingOccurrences(of: "\"LIVE\"", with: "\"\(status)\"")
                .replacingOccurrences(of: "\"round\": \"6\"", with: "\"round\": \"\(round)\"")
            return try decode(Match.self, json + "}")
        }
        let season = [try match("3", "NS", days: -40),  // postponed, never replayed: not the current round
                      try match("8", "FT", days: -7), try match("9", "FT", days: -1), try match("9", "NS", days: 1),
                      try match("10", "NS", days: 7)]
        XCTAssertEqual(season.currentRound, "9")
        XCTAssertNil(Array(season.prefix(3)).currentRound)  // season over: stay at the top
    }

    func testPlayerWithoutPositionDecodes() throws {
        let page = try decode(PlayerPage.self, """
        {"id": 1, "name": "Lineup Only", "photo_url": null, "country": null,
         "position": null, "birth_date": null, "club": null, "matches": [], "seasons": [], "career": []}
        """)
        XCTAssertNil(page.position)
    }

    func testMatchLineupsDecode() throws {
        let page = try decode(MatchPage.self, matchJSON + """
        , "details": null, "lineups": {"home": {"formation": "4-3-3", "starters": [{"player": {"id": 7, "name": "Bruno Silva",
          "photo_url": null}, "shirt_number": 9, "position": "FW", "x": 0.5, "y": 0.87, "rating": 7.4, "captain": true,
          "sub_in": null, "sub_out": 78}], "subs": [], "coach": null, "unavailable": [{"player": {"id": 8, "name": "A B",
          "photo_url": null}, "reason": "injury", "expected_return": null}]}, "away": null}}
        """)
        XCTAssertEqual(page.lineups?.home?.starters.first?.subOut, 78)
        XCTAssertEqual(page.lineups?.home?.unavailable.first?.reason, "injury")
        XCTAssertNil(page.lineups?.away)
        XCTAssertNil(page.lineups?.title)  // no type (older answers) or "standard": the confirmed lineup, no title
        XCTAssertEqual(page.lineups?.hasStarters, true)
        XCTAssertNil(try decode(MatchPage.self, matchJSON + #", "details": null, "lineups": null}"#).lineups)
        let context = try decode(MatchPage.self, matchJSON + #", "details": null, "lineups": null, "form": {"home": ["W", "D"], "away": []}, "h2h": {"matches": 2, "home_wins": 1, "draws": 1, "away_wins": 0}}"#)
        XCTAssertEqual(context.form?.home, ["W", "D"])
        XCTAssertEqual(context.h2h?.homeWins, 1)
    }

    func testPlayerPageDecodes() throws {
        let page = try decode(PlayerPage.self, """
        {"id": 1467236, "name": "Lamine Yamal", "photo_url": null,
         "country": {"id": 6720, "name": "Spain", "logo_url": "https://images.fotmob.com/image_resources/logo/teamlogo/esp.png"},
         "position": "FW", "birth_date": "2007-07-13", "club": {"id": 8634, "name": "Barcelona", "logo_url": null},
         "matches": [\(matchJSON), "rating": 8.1, "minutes": 78, "role": "starter"}],
         "seasons": [{"season": "2025/2026", "competition": {"id": 87, "name": "LaLiga", "logo_url": null},
           "team": {"id": 8634, "name": "Barcelona", "logo_url": null}, "appearances": 30, "goals": 12, "assists": 15,
           "rating": 7.9}],
         "career": [{"id": 5, "kind": "senior", "team": {"id": null, "name": "Barcelona B", "logo_url": null},
           "start_date": "2023-04-29", "end_date": null, "appearances": 2, "goals": 0, "assists": 0}]}
        """)
        XCTAssertEqual(page.country?.name, "Spain")
        XCTAssertEqual(page.club?.id, 8634)
        XCTAssertEqual(page.matches.first?.minutes, 78)
        XCTAssertEqual(page.matches.first?.goals, 0)  // absent in older answers: none
        XCTAssertEqual(Contributions.spoken(goals: 2, assists: 1), "2 goals, 1 assist")
        XCTAssertEqual(page.matches.first?.match.home.name, "Coventry City")
        XCTAssertEqual(page.seasons.first?.competition.name, "LaLiga")
        XCTAssertNil(page.career.first?.team.id)
    }

    func testTeamTransfersDecode() throws {
        let team = try decode(TeamPage.self, """
        {"id": 8634, "name": "Barcelona", "short_name": "Barcelona", "logo_url": null, "squad": [], "last": [], "next": [],
         "transfers": {"arrivals": [{"player": {"id": 1, "name": "A", "photo_url": null},
           "team": {"id": 9, "name": "Leeds United", "logo_url": null}, "date": "2026-07-01T00:00:00Z",
           "fee_eur": 45000000, "fee_text": "fee", "on_loan": false}],
          "departures": [{"player": {"id": 2, "name": "B", "photo_url": null}, "team": null,
           "date": "2026-08-01T00:00:00+00:00", "fee_eur": null, "fee_text": "on loan", "on_loan": true}]},
         "standings": [{"competition": {"slug": "laliga", "name": "LaLiga", "logo_url": null}, "season": "2026/2027",
           "groups": [{"group": "", "rows": []}]}],
         "country": {"id": 6720, "name": "Spain", "logo_url": null},
         "venue": {"name": "Spotify Camp Nou", "city": "Barcelona", "capacity": 99787, "opened": 1957},
         "trophies": [{"competition": {"id": 87, "name": "LaLiga", "logo_url": null}, "won": 29, "runner_up": 28,
           "seasons_won": ["2025/2026"], "seasons_runner_up": []}]}
        """)
        XCTAssertEqual(team.transfers.arrivals.first?.team?.name, "Leeds United")
        XCTAssertEqual(team.transfers.arrivals.first?.feeEur, 45_000_000)
        XCTAssertNil(team.transfers.departures.first?.team)
        XCTAssertEqual(team.standings.first?.competition.name, "LaLiga")
        XCTAssertEqual(team.venue?.capacity, 99787)
        XCTAssertEqual(team.country?.id, 6720)
        XCTAssertEqual(team.trophies.first?.runnerUp, 28)
    }

    func testPitchLayout() {
        let size = CGSize(width: 300, height: 450)  // half depth: 450 / 2 − 30 − 30 = 165
        let keeper = PitchLayout.point(x: 0.5, y: 0.1, home: true, in: size)
        XCTAssertEqual(keeper.x, 150, accuracy: 0.001)
        XCTAssertEqual(keeper.y, 30, accuracy: 0.001)  // the keeper sits at the inset
        XCTAssertEqual(PitchLayout.point(x: 0.5, y: 0.1, home: false, in: size).y, 420, accuracy: 0.001)
        XCTAssertEqual(PitchLayout.point(x: 0.2, y: 0.5, home: false, in: size).x, 240, accuracy: 0.001)  // mirrored
        let homeFront = PitchLayout.point(x: 0.5, y: 0.87, home: true, in: size)
        let awayFront = PitchLayout.point(x: 0.5, y: 0.87, home: false, in: size)
        XCTAssertEqual(awayFront.y - homeFront.y, 2 * PitchLayout.midGap, accuracy: 0.001)
        XCTAssertEqual(PitchLayout.point(x: 0.5, y: 0.02, home: true, in: size).y, 30, accuracy: 0.001)  // clamped
        // smallest phone (iPhone SE): pitch 327 pt wide at 9:16 — lines 0.192 apart stay ≥ one ~56-pt cell apart
        let phone = CGSize(width: 327, height: 327 * 16 / 9)
        let defence = PitchLayout.point(x: 0.5, y: 0.29, home: true, in: phone)
        let midfield = PitchLayout.point(x: 0.5, y: 0.482, home: true, in: phone)
        XCTAssertGreaterThanOrEqual(midfield.y - defence.y, 56)
    }

    func testCareerYears() throws {
        func entry(_ start: String?, _ end: String?) throws -> CareerEntry {
            let json = """
            {"id": 1, "kind": "senior", "team": {"id": null, "name": "X", "logo_url": null},
             "start_date": \(start.map { "\"\($0)\"" } ?? "null"), "end_date": \(end.map { "\"\($0)\"" } ?? "null"),
             "appearances": null, "goals": null, "assists": null}
            """
            return try decode(CareerEntry.self, json)
        }
        XCTAssertEqual(try entry("2022-07-01", nil).years, "2022 – now")
        XCTAssertEqual(try entry("2016-07-01", "2022-06-30").years, "2016 – 2022")
    }

    func testAgeLineKeepsTheBirthDayInAnyTimeZone() {
        let saved = NSTimeZone.default
        defer { NSTimeZone.default = saved }
        NSTimeZone.default = TimeZone(identifier: "Pacific/Auckland")!
        let now = ISO8601DateFormatter().date(from: "2026-10-15T12:00:00Z")!
        XCTAssertEqual(PlayerPage.ageLine(birthDate: "2000-07-21", now: now), "26 (21 Jul 2000)")
        XCTAssertNil(PlayerPage.ageLine(birthDate: "not a date", now: now))
    }

    func testTransferFeeLabels() {
        func move(_ fee: Int?, _ text: String?, loan: Bool = false) -> Transfer {
            Transfer(player: PlayerRef(id: 1, name: "A", photoUrl: nil), team: nil, date: .now, feeEur: fee,
                     feeText: text, onLoan: loan)
        }
        XCTAssertEqual(move(45_000_000, "fee").feeLabel, "€45M")
        XCTAssertEqual(move(1_500_000, "fee").feeLabel, "€1.5M")
        XCTAssertEqual(move(nil, "on loan", loan: true).feeLabel, "Loan")
        XCTAssertEqual(move(nil, "free transfer").feeLabel, "Free")
        XCTAssertEqual(move(nil, "undisclosed").feeLabel, "Undisclosed")
        XCTAssertEqual(move(nil, nil).feeLabel, "—")
    }
}
