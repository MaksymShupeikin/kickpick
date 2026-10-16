import Foundation

struct TeamRef: Codable, Hashable, Identifiable {
    let id: Int
    let name: String
    let shortName: String?
    let logoUrl: URL?
}

struct CompetitionRef: Codable, Hashable {
    let slug: String
    let name: String
    var kind: String? = nil  // "league", "cup", "international"
    let logoUrl: URL?
}

struct Competition: Codable, Hashable, Identifiable {
    var id: String { slug }
    let slug: String
    let name: String
    let kind: String
    let currentSeason: String?
    let logoUrl: URL?
}

enum MatchStatus: String, Codable {
    case notStarted = "NS", live = "LIVE", finished = "FT", cancelled = "CANC"

    var allowsPrediction: Bool { self == .notStarted || self == .live }
}

struct Match: Codable, Hashable, Identifiable {
    let id: Int
    let competition: CompetitionRef
    let season: String
    let round: String
    let kickoff: Date
    let status: MatchStatus
    let minute: String?
    let home: TeamRef
    let away: TeamRef
    let homeScore: Int?
    let awayScore: Int?
}

struct MatchEvent: Codable, Hashable {
    let minute: Int
    let added: Int?
    let type: String
    let side: String
    let player: String?
    let assist: String?
    let note: String?
    let score: String?
    let playerId: Int?  // nil when the name has no unique match in the lineup

    var minuteText: String { added.map { "\(minute)+\($0)'" } ?? "\(minute)'" }
}

struct MatchStat: Codable, Hashable {
    let name: String
    let home: String
    let away: String

    var homeValue: Double { Self.number(home) }
    var awayValue: Double { Self.number(away) }

    /// "185 (70%)" → 185, "1.47" → 1.47
    static func number(_ text: String) -> Double {
        Double(text.prefix { $0.isNumber || $0 == "." }) ?? 0
    }
}

struct MatchDetails: Codable, Hashable {
    let events: [MatchEvent]
    let stats: [MatchStat]
}

struct MatchPrediction: Decodable, Hashable {
    struct Probabilities: Decodable, Hashable {
        let home: Double
        let draw: Double
        let away: Double

        var highest: Double { max(home, draw, away) }
        var isValid: Bool {
            [home, draw, away].allSatisfy { $0.isFinite && (0...1).contains($0) }
                && abs(home + draw + away - 1) < 0.000001
        }
    }

    let probabilities: Probabilities
    let generatedAt: Date

    private enum CodingKeys: String, CodingKey { case probabilities, generatedAt }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        probabilities = try container.decode(Probabilities.self, forKey: .probabilities)
        generatedAt = try container.decode(Date.self, forKey: .generatedAt)
        guard probabilities.isValid else {
            throw DecodingError.dataCorruptedError(forKey: .probabilities, in: container,
                                                   debugDescription: "Invalid outcome probabilities")
        }
    }
}

/// `/matches/{id}`: match details and an optional saved pre-match prediction.
struct MatchPage: Decodable {
    let match: Match
    let details: MatchDetails?
    let lineups: Lineups?
    let form: Form?
    let h2h: HeadToHead?
    let prediction: MatchPrediction?

    /// Waiting for a forecast: the worker publishes every 10 min. Near kickoff
    /// and while live, keep the normal 15 s score updates; stop after completion.
    var refreshInterval: Duration? {
        guard match.status.allowsPrediction else { return nil }
        return match.needsPolling ? .seconds(15) : .seconds(600)
    }

    private enum Keys: String, CodingKey { case details, lineups, form, h2h, prediction }

    init(from decoder: Decoder) throws {
        match = try Match(from: decoder)
        let container = try decoder.container(keyedBy: Keys.self)
        details = try container.decodeIfPresent(MatchDetails.self, forKey: .details)
        lineups = try container.decodeIfPresent(Lineups.self, forKey: .lineups)
        form = try container.decodeIfPresent(Form.self, forKey: .form)
        h2h = try container.decodeIfPresent(HeadToHead.self, forKey: .h2h)
        // An optional forecast must never prevent scores/lineups loading. Also
        // reject finished/cancelled matches and forecasts generated after kickoff.
        let saved = try? container.decodeIfPresent(MatchPrediction.self, forKey: .prediction)
        prediction = match.status.allowsPrediction && (saved?.generatedAt ?? .distantFuture) < match.kickoff ? saved : nil
    }
}

/// Each side's last 5 finished matches before this one, oldest first: "W" / "D" / "L".
struct Form: Codable, Hashable {
    let home: [String]
    let away: [String]
}

/// The last 5 finished meetings, counted for this match's home and away team.
struct HeadToHead: Codable, Hashable {
    let matches: Int
    let homeWins: Int
    let draws: Int
    let awayWins: Int
}

struct Lineups: Codable, Hashable {
    let home: TeamLineup?
    let away: TeamLineup?
    let type: String?  // "standard" (confirmed), "predicted", "lastStarting11" (the previous XI), "unavailable"

    /// Over the pitch when it isn't the confirmed lineup.
    var title: String? {
        switch type {
        case "predicted": "Predicted lineups"
        case "lastStarting11": "Last starting lineups"
        default: nil
        }
    }

    var hasStarters: Bool { !(home?.starters.isEmpty ?? true) || !(away?.starters.isEmpty ?? true) }
}

struct TeamLineup: Codable, Hashable {
    let formation: String?
    let starters: [LineupPlayer]
    let subs: [LineupPlayer]
    let coach: PlayerRef?
    let unavailable: [Absence]
}

/// x (0 left … 1 right) and y (0 own goal … 1 halfway) are within the team's own half.
struct LineupPlayer: Codable, Hashable, Identifiable {
    var id: Int { player.id }
    let player: PlayerRef
    let shirtNumber: Int?
    let position: String?
    let x: Double?
    let y: Double?
    let rating: Double?
    let captain: Bool
    let subIn: Int?
    let subOut: Int?
    let goals: Int?
    let assists: Int?
    let flagUrl: URL?  // where he's from
}

struct Absence: Codable, Hashable, Identifiable {
    var id: Int { player.id }
    let player: PlayerRef
    let reason: String?
    let expectedReturn: String?
}

/// A club or competition the app may not know: any field can be missing.
struct NamedRef: Codable, Hashable {
    let id: Int?
    let name: String?
    let logoUrl: URL?
}

struct StandingRow: Codable, Hashable, Identifiable {
    var id: Int { team.id }
    let position: Int
    let team: TeamRef
    let played: Int
    let won: Int
    let drawn: Int
    let lost: Int
    let goalsFor: Int
    let goalsAgainst: Int
    let points: Int
    let zoneColor: String?  // "#2AD572": the zone the row is in (Champions League, relegation…), as FotMob colours it
}

struct StandingGroup: Codable, Hashable {
    let group: String
    let rows: [StandingRow]
    let legend: [Zone]?  // the zones this table's rows are in
}

/// What a standings colour means: "Champions League", "Relegation", "Qualification to 1/8 finals"…
struct Zone: Codable, Hashable {
    let title: String
    let color: String

    /// Every zone of the tables shown, once, in order: the legend under them.
    static func legend(of groups: [StandingGroup]) -> [Zone] {
        var seen = Set<String>()
        return groups.flatMap { $0.legend ?? [] }.filter { seen.insert($0.color).inserted }
    }
}

struct Matchup: Codable, Hashable {
    let home: TeamRef?
    let away: TeamRef?
    let homeScore: Int?
    let awayScore: Int?
    let winnerId: Int?
    let matchIds: [Int]
}

struct BracketRound: Codable, Hashable {
    let stage: String
    let matchups: [Matchup]
}

struct Bracket: Codable, Hashable {
    let rounds: [BracketRound]
    let thirdPlace: Matchup?
}

struct PlayerRef: Codable, Hashable {
    let id: Int
    let name: String
    let photoUrl: URL?
}

struct SquadEntry: Codable, Hashable, Identifiable {
    var id: Int { player.id }
    let player: PlayerRef
    let shirtNumber: Int?
    let position: String?
    let flagUrl: URL?
    let countryName: String?
    let club: NamedRef?  // in a national side's squad: the player's club, shown instead of a flag
}

struct TeamPage: Codable, Hashable {
    let id: Int
    let name: String
    let shortName: String
    let logoUrl: URL?
    let squad: [SquadEntry]
    let last: [Match]
    let next: [Match]
    let transfers: Transfers
    let standings: [TeamStandings]
    let venue: Venue?
    let trophies: [Trophy]
    let country: NamedRef?  // the flag, linked to the national team when we have its page
}

struct Venue: Codable, Hashable {
    let name: String
    let city: String?
    let capacity: Int?
    let opened: Int?
}

/// One competition the club has won or finished second in, with the seasons (newest first).
struct Trophy: Codable, Hashable, Identifiable {
    let competition: NamedRef
    let won: Int
    let runnerUp: Int
    let seasonsWon: [String]
    let seasonsRunnerUp: [String]
    var id: String { "\(competition.id ?? 0)-\(competition.name ?? "")" }
}

/// One of the team's current tables: only the groups it is in.
struct TeamStandings: Codable, Hashable {
    let competition: CompetitionRef
    let season: String
    let groups: [StandingGroup]
}

struct Transfers: Codable, Hashable {
    let arrivals: [Transfer]
    let departures: [Transfer]
}

/// `team` is the other club: where he came from, or where he went.
struct Transfer: Codable, Hashable, Identifiable {
    var id: String { "\(player.id)|\(date.timeIntervalSince1970)" }
    let player: PlayerRef
    let team: NamedRef?
    let date: Date
    let feeEur: Int?
    let feeText: String?
    let onLoan: Bool
}

struct PlayerPage: Decodable, Hashable {
    let id: Int
    let name: String
    let photoUrl: URL?
    let position: String?
    let birthDate: String?
    let heightCm: Int?
    let foot: String?
    let marketValueEur: Int?
    let contractEnd: String?
    let club: NamedRef?  // id nil: a club we have no page for
    let country: NamedRef?  // the flag, linked to the national team when we have its page
    let matches: [PlayerMatch]
    let seasons: [SeasonStats]
    let career: [CareerEntry]
}

/// A match he played: the match fields plus his rating and minutes on the pitch.
struct PlayerMatch: Decodable, Hashable, Identifiable {
    let match: Match
    let rating: Double?
    let minutes: Int
    let goals: Int
    let assists: Int
    var id: Int { match.id }

    private enum Keys: String, CodingKey { case rating, minutes, goals, assists }

    init(from decoder: Decoder) throws {
        match = try Match(from: decoder)
        let container = try decoder.container(keyedBy: Keys.self)
        rating = try container.decodeIfPresent(Double.self, forKey: .rating)
        minutes = try container.decode(Int.self, forKey: .minutes)
        goals = try container.decodeIfPresent(Int.self, forKey: .goals) ?? 0
        assists = try container.decodeIfPresent(Int.self, forKey: .assists) ?? 0
    }
}

struct SeasonStats: Codable, Hashable, Identifiable {
    var id: String { "\(season)|\(competition.id ?? 0)|\(team.id ?? 0)" }
    let season: String
    let competition: NamedRef
    let team: NamedRef
    let appearances: Int?
    let goals: Int?
    let assists: Int?
    let rating: Double?
}

struct CareerEntry: Codable, Hashable, Identifiable {
    let id: Int
    let kind: String
    let team: NamedRef
    let startDate: String?
    let endDate: String?
    let appearances: Int?
    let goals: Int?
    let assists: Int?
}

/// Shown before anything is typed: the top match of the moment, the side that leads or won it, its best player.
struct SearchSuggestions: Codable, Hashable {
    let match: Match?
    let team: TeamRef?
    let player: PlayerHit?
}

struct PlayerHit: Codable, Hashable, Identifiable {
    let id: Int
    let name: String
    let photoUrl: URL?
    let teamName: String?
}

struct SearchResults: Codable, Hashable {
    let competitions: [Competition]
    let teams: [TeamRef]
    let players: [PlayerHit]
    let matches: [Match]

    var isEmpty: Bool { competitions.isEmpty && teams.isEmpty && players.isEmpty && matches.isEmpty }
}

extension JSONDecoder {
    static let api: JSONDecoder = {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let plain = ISO8601DateFormatter()
        let fractional = ISO8601DateFormatter()
        fractional.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        decoder.dateDecodingStrategy = .custom { decoder in
            let text = try decoder.singleValueContainer().decode(String.self)
            guard let date = plain.date(from: text) ?? fractional.date(from: text) else {
                throw DecodingError.dataCorrupted(.init(codingPath: decoder.codingPath, debugDescription: "Bad date \(text)"))
            }
            return date
        }
        return decoder
    }()
}
