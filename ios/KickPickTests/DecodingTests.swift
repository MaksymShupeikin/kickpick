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
        XCTAssertTrue(old.statusText(showDate: true).hasSuffix("\n2022"))
        let recent = try decode(Match.self, matchJSON.replacingOccurrences(of: "2026-10-12T19", with: ISO8601DateFormatter().string(from: .now).prefix(13))
            .replacingOccurrences(of: "LIVE", with: "FT") + "}")
        XCTAssertFalse(recent.statusText(showDate: true).contains("\n"))
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

    func testPlayerWithoutPositionDecodes() throws {
        let page = try decode(PlayerPage.self, """
        {"id": 1, "name": "Lineup Only", "photo_url": null, "country_code": null, "country_name": null, "flag_url": null,
         "position": null, "birth_date": null, "teams": [], "matches": [], "seasons": [], "career": []}
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
        XCTAssertNil(try decode(MatchPage.self, matchJSON + #", "details": null, "lineups": null}"#).lineups)
    }

    func testPlayerPageDecodes() throws {
        let page = try decode(PlayerPage.self, """
        {"id": 1467236, "name": "Lamine Yamal", "photo_url": null, "country_code": "ESP", "country_name": "Spain",
         "flag_url": "https://images.fotmob.com/image_resources/logo/teamlogo/esp.png", "position": "FW",
         "birth_date": "2007-07-13", "teams": [],
         "matches": [\(matchJSON), "rating": 8.1, "minutes": 78, "role": "starter"}],
         "seasons": [{"season": "2025/2026", "competition": {"id": 87, "name": "LaLiga", "logo_url": null},
           "team": {"id": 8634, "name": "Barcelona", "logo_url": null}, "appearances": 30, "goals": 12, "assists": 15,
           "rating": 7.9}],
         "career": [{"id": 5, "kind": "senior", "team": {"id": null, "name": "Barcelona B", "logo_url": null},
           "start_date": "2023-04-29", "end_date": null, "appearances": 2, "goals": 0, "assists": 0}]}
        """)
        XCTAssertEqual(page.countryName, "Spain")
        XCTAssertEqual(page.matches.first?.minutes, 78)
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
           "date": "2026-08-01T00:00:00+00:00", "fee_eur": null, "fee_text": "on loan", "on_loan": true}]}}
        """)
        XCTAssertEqual(team.transfers.arrivals.first?.team?.name, "Leeds United")
        XCTAssertEqual(team.transfers.arrivals.first?.feeEur, 45_000_000)
        XCTAssertNil(team.transfers.departures.first?.team)
    }

    func testPitchLayout() {
        let size = CGSize(width: 300, height: 450)  // half depth: 450 / 2 − 40 − 40 = 145
        let keeper = PitchLayout.point(x: 0.5, y: 0.1, home: true, in: size)
        XCTAssertEqual(keeper.x, 150, accuracy: 0.001)
        XCTAssertEqual(keeper.y, 40 + 0.1 * 145, accuracy: 0.001)
        XCTAssertEqual(PitchLayout.point(x: 0.5, y: 0.1, home: false, in: size).y, 450 - 40 - 0.1 * 145, accuracy: 0.001)
        XCTAssertEqual(PitchLayout.point(x: 0.2, y: 0.5, home: false, in: size).x, 240, accuracy: 0.001)  // mirrored
        let homeFront = PitchLayout.point(x: 0.5, y: 1, home: true, in: size)
        let awayFront = PitchLayout.point(x: 0.5, y: 1, home: false, in: size)
        XCTAssertGreaterThanOrEqual(awayFront.y - homeFront.y, 2 * PitchLayout.midGap)
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
        XCTAssertEqual(PlayerPage.ageLine(birthDate: "2000-07-21", now: now), "26 · 21 Jul 2000")
        XCTAssertNil(PlayerPage.ageLine(birthDate: "not a date", now: now))
    }
}
