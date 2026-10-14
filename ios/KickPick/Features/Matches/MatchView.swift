import SwiftUI

struct MatchView: View {
    let id: Int
    @State private var tab: Tab?  // nil until picked: the default depends on whether the match has started

    enum Tab: Hashable { case events, stats, lineups }

    var body: some View {
        ScrollView {
            Loader(live: { $0.match.needsPolling }) { try await APIClient.shared.match(id) } content: { page in
                let selected = tab ?? (page.match.status == .notStarted ? .lineups : .events)
                VStack(spacing: 24) {
                    VStack(spacing: 12) {
                        MatchHeader(match: page.match)
                            .accessibilityAddTraits(.isHeader)
                            .revealsInBar { MiniScore(match: page.match) }
                        CompetitionLine(match: page.match)
                    }
                    SegmentedPicker(options: [(.events, "Events"), (.stats, "Stats"), (.lineups, "Lineups")],
                                    selection: Binding(get: { selected }, set: { tab = $0 }))
                    switch selected {
                    case .events:
                        if let events = page.details?.events, !events.isEmpty {
                            EventsCard(events: events)
                        } else {
                            EmptyState(text: "No events yet")
                        }
                    case .stats:
                        if let stats = page.details?.stats, !stats.isEmpty {
                            StatsCard(stats: stats)
                        } else {
                            EmptyState(text: "No stats yet")
                        }
                    case .lineups:
                        if let lineups = page.lineups {
                            LineupsView(match: page.match, lineups: lineups)
                        } else {
                            EmptyState(text: "No lineups yet")
                        }
                    }
                }
                .onAppear { if tab == nil { tab = selected } }
            }
            .padding(16)
        }
        .screen()
        .navigationBarTitleDisplayMode(.inline)
    }
}

/// Bar version of the header: both crests and the score (kick-off time before the start).
private struct MiniScore: View {
    let match: Match

    var body: some View {
        HStack(spacing: 10) {
            Logo(url: match.home.logoUrl, size: 24, label: match.home.name)
            Text(match.homeScore.map { "\($0) – \(match.awayScore ?? 0)" }
                 ?? match.kickoff.formatted(.dateTime.hour().minute().locale(.app)))
                .font(.digits(20, relativeTo: .headline))
                .monospacedDigit()
                .foregroundStyle(Color.textPrimary)
            Logo(url: match.away.logoUrl, size: 24, label: match.away.name)
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(match.spokenSummary)
    }
}

/// "Premier League · Matchday 7" under the header card.
private struct CompetitionLine: View {
    let match: Match

    var body: some View {
        HStack(spacing: 8) {
            Logo(url: match.competition.logoUrl, size: 20, label: match.competition.name)
                .accessibilityHidden(true)
            Text(match.round.isEmpty ? match.competition.name : "\(match.competition.name) · \(roundTitle(match.round))")
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(Color.textSecondary)
                .lineLimit(1)
        }
        .frame(maxWidth: .infinity)
        .accessibilityElement(children: .combine)
    }
}

private struct MatchHeader: View {
    let match: Match

    var body: some View {
        HStack(alignment: .top, spacing: 8) {
            side(match.home)
            VStack(spacing: 4) {
                Text(match.homeScore.map { "\($0) – \(match.awayScore ?? 0)" } ?? "–")
                    .font(.digits(48, relativeTo: .largeTitle))
                    .monospacedDigit()
                    .foregroundStyle(Color.textPrimary)
                if match.status == .notStarted {
                    Text(match.kickoff.formatted(.dateTime.day().month().hour().minute().locale(.app)))
                        .font(.footnote.weight(.medium)).foregroundStyle(Color.textSecondary)
                } else {
                    MatchStatusText(match: match)
                }
            }
            .frame(minWidth: 110)
            side(match.away)
        }
        .padding(16)
        .frame(maxWidth: .infinity)
        .glassCard()
    }

    private func side(_ team: TeamRef) -> some View {
        NavigationLink(value: Route.team(team.id)) {
            VStack(spacing: 8) {
                Logo(url: team.logoUrl, size: 64, label: team.name)
                Text(team.name)
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(Color.textPrimary)
                    .multilineTextAlignment(.center)
                    .lineLimit(2)
            }
            .frame(maxWidth: .infinity)
        }
        .buttonStyle(.plain)
    }
}

private struct EventsCard: View {
    let events: [MatchEvent]

    var body: some View {
        VStack(spacing: 0) {
            ForEach(events.indices, id: \.self) { index in
                if index > 0 { Hairline() }
                EventRow(event: events[index])
            }
        }
        .glassCard()
    }
}

private struct EventRow: View {
    let event: MatchEvent

    var body: some View {
        let home = event.side == "home"
        HStack(spacing: 10) {
            if home {
                minute
                EventIcon(type: event.type)
                names(alignment: .leading)
                Spacer(minLength: 0)
            } else {
                Spacer(minLength: 0)
                names(alignment: .trailing)
                EventIcon(type: event.type)
                minute
            }
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 10)
        .accessibilityElement(children: .combine)
    }

    private var minute: some View {
        Text(event.minuteText)
            .font(.digits(17, relativeTo: .body, bold: false))
            .foregroundStyle(Color.textSecondary)
            .frame(width: 40, alignment: event.side == "home" ? .leading : .trailing)
    }

    private func names(alignment: HorizontalAlignment) -> some View {
        VStack(alignment: alignment, spacing: 2) {
            Text(event.player ?? "—").font(.subheadline.weight(.semibold)).foregroundStyle(Color.textPrimary)
            if let detail = event.detail {
                Text(detail).font(.footnote).foregroundStyle(Color.textSecondary)
            }
        }
    }
}

private extension MatchEvent {
    var detail: String? {
        switch type {
        case "sub": return note
        case "own_goal": return "Own goal"
        case "goal": return assist ?? (note == "Penalty" ? "Penalty" : nil)
        default: return nil
        }
    }
}

private struct EventIcon: View {
    let type: String

    var body: some View {
        switch type {
        case "goal":
            Image(systemName: "soccerball").foregroundStyle(Color.textPrimary).accessibilityLabel("Goal")
        case "own_goal":
            Image(systemName: "soccerball").foregroundStyle(Color.textPrimary).accessibilityLabel("Own goal")
        case "yellow":
            card(Color.cardYellow).accessibilityLabel("Yellow card")
        case "red":
            card(Color.cardRed).accessibilityLabel("Red card")
        case "second_yellow":
            card(Color.cardRed).accessibilityLabel("Second yellow")
        case "sub":
            Image(systemName: "arrow.left.arrow.right").foregroundStyle(Color.textPrimary).accessibilityLabel("Substitution")
        default:
            EmptyView()
        }
    }

    private func card(_ color: Color) -> some View {
        RoundedRectangle(cornerRadius: 1.5).fill(color).frame(width: 8, height: 11)
    }
}

private struct StatsCard: View {
    let stats: [MatchStat]

    var body: some View {
        VStack(spacing: 14) {
            ForEach(stats, id: \.name) { stat in
                VStack(spacing: 6) {
                    HStack {
                        Text(stat.home).font(.digits(17, relativeTo: .body, bold: false)).foregroundStyle(Color.textPrimary)
                        Spacer()
                        Text(stat.name)
                            .font(.footnote.weight(.medium)).foregroundStyle(Color.textSecondary)
                        Spacer()
                        Text(stat.away).font(.digits(17, relativeTo: .body, bold: false)).foregroundStyle(Color.textPrimary)
                    }
                    ShareBar(home: stat.homeValue, away: stat.awayValue)
                }
                .accessibilityElement(children: .combine)
            }
        }
        .padding(16)
        .glassCard()
    }
}

private struct ShareBar: View {
    let home: Double
    let away: Double

    var body: some View {
        GeometryReader { geo in
            let total = home + away
            let share = total > 0 ? home / total : 0.5
            HStack(spacing: 2) {
                Capsule().fill(Color.white).frame(width: max(0, geo.size.width * share - 1))
                Capsule().fill(Color.white.opacity(0.3))
            }
        }
        .frame(height: 4)
        .accessibilityHidden(true)
    }
}
