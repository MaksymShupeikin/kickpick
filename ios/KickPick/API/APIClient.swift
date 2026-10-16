import Foundation

enum APIError: Error {
    case status(Int)
}

struct APIClient {
    static let shared = APIClient(
        base: URL(string: Bundle.main.object(forInfoDictionaryKey: "APIBaseURL") as? String ?? "")
            ?? URL(string: "http://localhost:8000")!)

    let base: URL

    /// Always UTC with "Z": a "+03:00" offset would turn into a space in the query string.
    static func isoUTC(_ date: Date) -> String {
        ISO8601DateFormatter().string(from: date)
    }

    func get<T: Decodable>(_ path: String, query: [String: String] = [:]) async throws -> T {
        var components = URLComponents(url: base.appending(path: path), resolvingAgainstBaseURL: false)!
        if !query.isEmpty {
            components.queryItems = query.sorted { $0.key < $1.key }.map { URLQueryItem(name: $0.key, value: $0.value) }
        }
        for attempt in 0...1 {
            let (data, response) = try await URLSession.shared.data(from: components.url!)
            let http = response as? HTTPURLResponse
            let code = http?.statusCode ?? 0
            if code == 429, attempt == 0 {
                let seconds = Double(http?.value(forHTTPHeaderField: "Retry-After") ?? "") ?? 1
                try await Task.sleep(for: .seconds(min(max(seconds, 1), 30) + Double.random(in: 0.1...0.5)))
                continue  // honor the gateway's cooldown; retry at most once
            }
            guard code == 200 else { throw APIError.status(code) }
            return try JSONDecoder.api.decode(T.self, from: data)
        }
        throw APIError.status(429)
    }

    func competitions() async throws -> [Competition] { try await get("competitions") }
    func seasons(_ slug: String) async throws -> [String] { try await get("competitions/\(slug)/seasons") }

    func standings(_ slug: String, season: String?) async throws -> [StandingGroup] {
        try await get("competitions/\(slug)/standings", query: seasonQuery(season))
    }

    func matches(_ slug: String, season: String?) async throws -> [Match] {
        try await get("competitions/\(slug)/matches", query: seasonQuery(season))
    }

    func bracket(_ slug: String, season: String?) async throws -> Bracket? {
        do {
            return try await get("competitions/\(slug)/bracket", query: seasonQuery(season))
        } catch APIError.status(404) {
            return nil
        }
    }

    func matches(from: Date, to: Date) async throws -> [Match] {
        try await get("matches", query: ["from": Self.isoUTC(from), "to": Self.isoUTC(to)])
    }

    func match(_ id: Int) async throws -> MatchPage { try await get("matches/\(id)") }
    func team(_ id: Int) async throws -> TeamPage { try await get("teams/\(id)") }
    func player(_ id: Int) async throws -> PlayerPage { try await get("players/\(id)") }
    func search(_ text: String) async throws -> SearchResults { try await get("search", query: ["q": text]) }
    func searchSuggestions() async throws -> SearchSuggestions { try await get("search/suggestions") }

    private func seasonQuery(_ season: String?) -> [String: String] {
        season.map { ["season": $0] } ?? [:]
    }
}
