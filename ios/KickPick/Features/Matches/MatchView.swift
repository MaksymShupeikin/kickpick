import SwiftUI

struct MatchView: View {
    let id: Int

    var body: some View {
        ScrollView {
            Loader(live: { $0.match.status == .live }) { try await APIClient.shared.match(id) } content: { page in
                VStack(spacing: 16) {
                    MatchHeader(match: page.match)
                    if let details = page.details {
                        if !details.events.isEmpty { EventsCard(events: details.events) }
                        if !details.stats.isEmpty { StatsCard(stats: details.stats) }
                    }
                }
                .navigationTitle(page.match.competition.name)
            }
            .padding(16)
        }
        .screen()
        .navigationBarTitleDisplayMode(.inline)
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
        case "own_goal": return "Автогол"
        case "goal": return assist ?? (note == "Penalty" ? "Пенальти" : nil)
        default: return nil
        }
    }
}

private struct EventIcon: View {
    let type: String

    var body: some View {
        switch type {
        case "goal", "own_goal":
            Image(systemName: "soccerball").foregroundStyle(Color.textPrimary)
        case "yellow":
            card(Color.cardYellow)
        case "red", "second_yellow":
            card(Color.cardRed)
        case "sub":
            Image(systemName: "arrow.left.arrow.right").foregroundStyle(Color.textPrimary)
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
                        Text(Self.titles[stat.name] ?? stat.name)
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

    static let titles = [
        "Ball possession": "Владение", "Expected goals (xG)": "Ожидаемые голы (xG)", "Total shots": "Удары",
        "Shots on target": "В створ", "Big chances": "Голевые моменты", "Big chances missed": "Упущенные моменты",
        "Accurate passes": "Точные передачи", "Fouls committed": "Фолы", "Corners": "Угловые",
        "Yellow cards": "Жёлтые карточки", "Touches in opposition box": "Касания в штрафной",
    ]
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
