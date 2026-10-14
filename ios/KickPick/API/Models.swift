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

/// `/matches/{id}`: the match fields plus `details`.
struct MatchPage: Decodable {
    let match: Match
    let details: MatchDetails?

    private enum Keys: String, CodingKey { case details }

    init(from decoder: Decoder) throws {
        match = try Match(from: decoder)
        details = try decoder.container(keyedBy: Keys.self).decodeIfPresent(MatchDetails.self, forKey: .details)
    }
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
    let position: String
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
}

struct Membership: Codable, Hashable, Identifiable {
    var id: Int { team.id }
    let team: TeamRef
    let shirtNumber: Int?
    let stats: PlayerStats
}

struct PlayerPage: Codable, Hashable {
    let id: Int
    let name: String
    let photoUrl: URL?
    let countryCode: String?
    let position: String
    let birthDate: String?
    let teams: [Membership]
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

    var isEmpty: Bool { competitions.isEmpty && teams.isEmpty && players.isEmpty }
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
