import SwiftUI

enum TeamWeight { case winner, loser, even }

extension Match {
    /// Live, or about to kick off / just started: mirrors the collector's polling window, so NS → LIVE is seen.
    var needsPolling: Bool {
        status == .live || (status == .notStarted && (-15 * 60...3 * 3600).contains(Date.now.timeIntervalSince(kickoff)))
    }

    func weight(home: Bool) -> TeamWeight {
        guard status == .finished, let h = homeScore, let a = awayScore, h != a else { return .even }
        return (h > a) == home ? .winner : .loser
    }

    /// The row's left column, plain text, never a chip (design.md §8). With the date: kick-off time (live: the
    /// minute) over "Today" / "14 Oct"; a match from another year has no use for its time, so "18 Dec" over "2022".
    /// Without (the day's feed, where the date strip names the day): the time alone.
    func statusLines(showDate: Bool) -> [String] {
        let time: String
        switch status {
        case .live: time = minute ?? "Live"
        case .cancelled: time = "Cancelled"
        case .finished, .notStarted: time = kickoff.formatted(.dateTime.hour().minute().locale(.app))
        }
        guard showDate else { return [time] }
        if status != .live && !Calendar.current.isDate(kickoff, equalTo: .now, toGranularity: .year) {
            return [kickoff.formatted(.dateTime.day().month(.abbreviated).locale(.app)),
                    kickoff.formatted(.dateTime.year().locale(.app))]
        }
        return [time, dayName]
    }

    /// "Today", "Tomorrow", "Yesterday", else "14 Oct".
    var dayName: String {
        let calendar = Calendar.current
        if calendar.isDateInToday(kickoff) { return "Today" }
        if calendar.isDateInTomorrow(kickoff) { return "Tomorrow" }
        if calendar.isDateInYesterday(kickoff) { return "Yesterday" }
        return kickoff.formatted(.dateTime.day().month(.abbreviated).locale(.app))
    }

    var spokenSummary: String {
        let teams = homeScore.map { "\(home.name) \($0), \(away.name) \(awayScore ?? 0)" } ?? "\(home.name) — \(away.name)"
        let state: String
        switch status {
        case .finished: state = "full time"
        case .live: state = minute.map { "live, \($0)" } ?? "live"
        case .notStarted: state = "kick-off " + kickoff.formatted(.dateTime.day().month().hour().minute().locale(.app))
        case .cancelled: state = "cancelled"
        }
        return "\(teams), \(state)"
    }

    static let placeholders: [Match] = (1...25).map { i in
        Match(id: -i, competition: CompetitionRef(slug: "placeholder", name: "Premier League", logoUrl: nil),
              season: "", round: "", kickoff: .now, status: .notStarted, minute: nil,
              home: TeamRef(id: -i, name: "Home team", shortName: nil, logoUrl: nil),
              away: TeamRef(id: -100 - i, name: "Away team", shortName: nil, logoUrl: nil),
              homeScore: nil, awayScore: nil)
    }
}

extension [Match] {
    /// The round of the earliest match still to finish, live or upcoming (kick-off order); nil once the season is over.
    /// A match postponed without a new date keeps its old kick-off and doesn't count.
    var currentRound: String? {
        let recent = Date.now.addingTimeInterval(-3 * 3600)
        return first { $0.status == .live || ($0.status == .notStarted && $0.kickoff > recent) }?.round
    }
}

struct MatchStatusText: View {
    let match: Match
    var showDate = true

    var body: some View {
        let live = match.status == .live
        VStack(alignment: .leading, spacing: 3) {
            // one Text per line ("21:00" / "Today"), so a long month shrinks instead of wrapping; the second line is
            // lighter and dimmer, so the two don't run together
            ForEach(Array(match.statusLines(showDate: showDate).enumerated()), id: \.offset) { index, line in
                HStack(spacing: 4) {
                    if live && index == 0 { Circle().fill(Color.cardRed).frame(width: 6, height: 6) }
                    Text(line)
                        .font(live && index == 0 ? .digits(22, relativeTo: .title3)
                              : index == 0 ? .footnote.weight(.semibold) : .footnote)
                        .foregroundStyle(live && index == 0 ? Color.textPrimary
                                         : index == 0 ? Color.textSecondary : Color.textTertiary)
                        .lineLimit(1)
                        .minimumScaleFactor(0.7)
                }
            }
        }
        .monospacedDigit()
    }
}

struct MatchRow: View {
    let match: Match
    var showDate = true  // false in the day's feed, where the date strip already says which day

    var body: some View {
        HStack(spacing: 8) {
            MatchStatusText(match: match, showDate: showDate).frame(width: 46, alignment: .leading)
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
