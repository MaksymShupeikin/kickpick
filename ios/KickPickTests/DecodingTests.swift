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
        XCTAssertTrue(live.spokenSummary.contains("идёт, 67'"))
        let done = try decode(Match.self, matchJSON.replacingOccurrences(of: "LIVE", with: "FT") + "}")
        XCTAssertTrue(done.spokenSummary.hasSuffix("завершён"))
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
         "players": [{"id": 1, "name": "Joan García", "photo_url": null, "team_name": "Barcelona"}]}
        """)
        XCTAssertEqual(results.competitions[0].currentSeason, "2026/2027")
        XCTAssertEqual(results.players[0].teamName, "Barcelona")
        XCTAssertFalse(results.isEmpty)
    }

    func testQueryDatesAreUTC() {
        let moscowMidnight = ISO8601DateFormatter().date(from: "2026-10-14T00:00:00+03:00")!
        XCTAssertEqual(APIClient.isoUTC(moscowMidnight), "2026-10-13T21:00:00Z")
    }

    func testRoundTitles() {
        XCTAssertEqual(roundTitle("7"), "Тур 7")
        XCTAssertEqual(roundTitle("1/8"), "1/8 финала")
        XCTAssertEqual(roundTitle("bronze"), "Матч за 3-е место")
        XCTAssertEqual(roundTitle("final"), "Финал")
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
}
