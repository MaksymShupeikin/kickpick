import SwiftUI

enum TeamWeight { case winner, loser, even }

extension Match {
    func weight(home: Bool) -> TeamWeight {
        guard status == .finished, let h = homeScore, let a = awayScore, h != a else { return .even }
        return (h > a) == home ? .winner : .loser
    }

    /// Plain text, never a chip (design.md §8).
    func statusText(showDate: Bool) -> String {
        let date = kickoff.formatted(.dateTime.day().month(.abbreviated).locale(.app))
        switch status {
        case .live: return minute ?? "Идёт"
        case .finished: return showDate ? date : "Конец"
        case .cancelled: return "Отменён"
        case .notStarted: return showDate ? date : kickoff.formatted(.dateTime.hour().minute().locale(.app))
        }
    }

    var spokenSummary: String {
        let teams = homeScore.map { "\(home.name) \($0), \(away.name) \(awayScore ?? 0)" } ?? "\(home.name) — \(away.name)"
        return "\(teams), \(statusText(showDate: true))"
    }

    static let placeholders: [Match] = (1...5).map { i in
        Match(id: -i, competition: CompetitionRef(slug: "placeholder", name: "Premier League", logoUrl: nil),
              season: "", round: "", kickoff: .now, status: .notStarted, minute: nil,
              home: TeamRef(id: -i, name: "Home team", shortName: nil, logoUrl: nil),
              away: TeamRef(id: -100 - i, name: "Away team", shortName: nil, logoUrl: nil),
              homeScore: nil, awayScore: nil)
    }
}

struct MatchStatusText: View {
    let match: Match
    var showDate = false

    var body: some View {
        HStack(spacing: 4) {
            if match.status == .live {
                Circle().fill(Color.cardRed).frame(width: 6, height: 6)
            }
            Text(match.statusText(showDate: showDate))
                .font(match.status == .live ? .digits(22, relativeTo: .title3) : .footnote.weight(.medium))
                .foregroundStyle(match.status == .live ? Color.textPrimary : Color.textSecondary)
                .monospacedDigit()
                .lineLimit(1)
                .minimumScaleFactor(0.7)
        }
    }
}

struct MatchRow: View {
    let match: Match
    var showDate = false

    var body: some View {
        HStack(spacing: 12) {
            MatchStatusText(match: match, showDate: showDate).frame(width: 52, alignment: .leading)
            VStack(spacing: 8) {
                TeamLine(team: match.home, score: match.homeScore, weight: match.weight(home: true))
                TeamLine(team: match.away, score: match.awayScore, weight: match.weight(home: false))
            }
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 12)
        .contentShape(Rectangle())
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(match.spokenSummary)
    }
}

private struct TeamLine: View {
    let team: TeamRef
    let score: Int?
    let weight: TeamWeight

    var body: some View {
        let color = weight == .loser ? Color.textSecondary : Color.textPrimary
        HStack(spacing: 10) {
            Logo(url: team.logoUrl, size: 24, label: team.name)
            Text(team.name)
                .font(.body.weight(weight == .winner ? .semibold : .regular))
                .foregroundStyle(color)
                .lineLimit(1)
            Spacer(minLength: 8)
            if let score {
                Text("\(score)").font(.digits(22, relativeTo: .title3)).monospacedDigit().foregroundStyle(color)
            }
        }
    }
}
