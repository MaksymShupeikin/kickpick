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

/// `/matches/{id}`: the match fields plus `details` and `lineups`.
struct MatchPage: Decodable {
    let match: Match
    let details: MatchDetails?
    let lineups: Lineups?

    private enum Keys: String, CodingKey { case details, lineups }

    init(from decoder: Decoder) throws {
        match = try Match(from: decoder)
        let container = try decoder.container(keyedBy: Keys.self)
        details = try container.decodeIfPresent(MatchDetails.self, forKey: .details)
        lineups = try container.decodeIfPresent(Lineups.self, forKey: .lineups)
    }
}

struct Lineups: Codable, Hashable {
    let home: TeamLineup?
    let away: TeamLineup?
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
}

struct StandingGroup: Codable, Hashable {
    let group: String
    let rows: [StandingRow]
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

struct PlayerStats: Codable, Hashable {
    let goals: Int?
    let assists: Int?
    let yellowCards: Int?
    let redCards: Int?
    let rating: Double?
}

struct SquadEntry: Codable, Hashable, Identifiable {
    var id: Int { player.id }
    let player: PlayerRef
    let shirtNumber: Int?
    let position: String?
    let stats: PlayerStats
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

struct Membership: Codable, Hashable, Identifiable {
    var id: Int { team.id }
    let team: TeamRef
    let shirtNumber: Int?
    let stats: PlayerStats
}

struct PlayerPage: Decodable, Hashable {
    let id: Int
    let name: String
    let photoUrl: URL?
    let countryCode: String?
    let countryName: String?
    let flagUrl: URL?
    let position: String?
    let birthDate: String?
    let teams: [Membership]
    let matches: [PlayerMatch]
    let seasons: [SeasonStats]
    let career: [CareerEntry]
}

/// A match he played: the match fields plus his rating and minutes on the pitch.
struct PlayerMatch: Decodable, Hashable, Identifiable {
    let match: Match
    let rating: Double?
    let minutes: Int
    var id: Int { match.id }

    private enum Keys: String, CodingKey { case rating, minutes }

    init(from decoder: Decoder) throws {
        match = try Match(from: decoder)
        let container = try decoder.container(keyedBy: Keys.self)
        rating = try container.decodeIfPresent(Double.self, forKey: .rating)
        minutes = try container.decode(Int.self, forKey: .minutes)
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
