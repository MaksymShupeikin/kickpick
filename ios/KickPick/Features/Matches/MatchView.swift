import SwiftUI

struct MatchView: View {
    let id: Int
    @State private var tab: Tab?  // nil until picked: the default depends on whether the match has started

    enum Tab: Hashable { case events, stats, lineups }

    var body: some View {
        ScrollView {
            Loader(skeleton: AnyView(MatchSkeleton()), refreshEvery: { $0.refreshInterval }) {
                try await APIClient.shared.match(id)
            } content: { page in
                let selected = tab ?? (page.match.status == .notStarted ? .lineups : .events)
                VStack(spacing: 24) {  // headers stay out of the lazy stack: their bar items must not unload
                    VStack(spacing: 12) {
                        CompetitionLine(match: page.match)
                        MatchHeader(match: page.match, events: page.details?.events ?? [])
                            .accessibilityAddTraits(.isHeader)
                            .revealsInBar { MiniScore(match: page.match) }
                        FormAndHeadToHead(match: page.match, form: page.form, h2h: page.h2h)
                    }
                    if page.match.status.allowsPrediction, let prediction = page.prediction {
                        PredictionCard(match: page.match, prediction: prediction)
                    }
                    LazyVStack(spacing: 24, pinnedViews: .sectionHeaders) {  // the tabs stick under the bar
                        Section {
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
                        } header: {
                            SegmentedPicker(options: [(.events, "Events"), (.stats, "Stats"), (.lineups, "Lineups")],
                                            selection: Binding(get: { selected }, set: { tab = $0 }))
                                .joinsBarWhenPinned()
                        }
                    }
                    .scrollsToTabs(on: selected)
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

/// One compact card under the score: each side's form and their head-to-head, home on the left like the card above.
/// Results are plain text (W / D / L), never chips (design.md §8).
private struct FormAndHeadToHead: View {
    let match: Match
    let form: Form?
    let h2h: HeadToHead?

    private var showsForm: Bool { !(form?.home.isEmpty ?? true) || !(form?.away.isEmpty ?? true) }
    private var meetings: HeadToHead? { h2h.flatMap { $0.matches > 0 ? $0 : nil } }

    var body: some View {
        if showsForm || meetings != nil {
            VStack(spacing: 0) {
                if let form, showsForm {
                    row("Form", home: results(form.home), away: results(form.away))
                        .accessibilityElement(children: .ignore)
                        .accessibilityLabel("Form, oldest first. \(match.home.name): \(spoken(form.home)). "
                                            + "\(match.away.name): \(spoken(form.away)).")
                }
                if let meetings {
                    if showsForm { Hairline() }
                    row("H2H", home: record(meetings.homeWins, meetings.draws, meetings.awayWins),
                        away: record(meetings.awayWins, meetings.draws, meetings.homeWins))
                        .accessibilityElement(children: .ignore)
                        .accessibilityLabel("Head to head, last \(meetings.matches): \(match.home.name) \(meetings.homeWins) "
                                            + "wins, \(meetings.draws) draws, \(meetings.awayWins) losses")
                }
            }
            .glassCard()
        }
    }

    private func row(_ title: String, home: some View, away: some View) -> some View {
        HStack(spacing: 8) {
            home.frame(maxWidth: .infinity, alignment: .leading)
            Text(title).font(.footnote.weight(.medium)).foregroundStyle(Color.textTertiary).fixedSize()
            away.frame(maxWidth: .infinity, alignment: .trailing)
        }
        .padding(.horizontal, 16)
        .frame(minHeight: 40)
    }

    private func results(_ list: [String]) -> some View {
        HStack(spacing: 6) {
            ForEach(Array(list.enumerated()), id: \.offset) { _, result in
                Text(result)
                    .font(.digits(17, relativeTo: .body))
                    .foregroundStyle(color(result))
            }
        }
    }

    /// "3W 0D 2L" from one side's point of view, letters in the form colours.
    private func record(_ wins: Int, _ draws: Int, _ losses: Int) -> some View {
        HStack(spacing: 8) {
            ForEach([(wins, "W"), (draws, "D"), (losses, "L")], id: \.1) { count, letter in
                HStack(spacing: 1) {
                    Text("\(count)").foregroundStyle(Color.textPrimary)
                    Text(letter).foregroundStyle(color(letter))
                }
            }
        }
        .font(.digits(17, relativeTo: .body))
    }

    private func color(_ result: String) -> Color {
        result == "W" ? .win : result == "L" ? .loss : .textSecondary
    }

    private func spoken(_ list: [String]) -> String {
        list.map { $0 == "W" ? "win" : $0 == "D" ? "draw" : "loss" }.joined(separator: ", ")
    }
}

/// Who scored, under each side of the score card: home on the left toward the middle, away on the right, a ball
/// between them.
private struct Scorers: View {
    let events: [MatchEvent]

    var body: some View {
        HStack(alignment: .top, spacing: 10) {
            column(events.scorerLines(side: "home"), alignment: .trailing)
            Image(systemName: "soccerball").font(.footnote).foregroundStyle(Color.textTertiary).accessibilityHidden(true)
            column(events.scorerLines(side: "away"), alignment: .leading)
        }
        .accessibilityElement(children: .combine)
        .accessibilityLabel("Goals: " + (events.scorerLines(side: "home") + events.scorerLines(side: "away")).joined(separator: ", "))
    }

    private func column(_ lines: [String], alignment: HorizontalAlignment) -> some View {
        VStack(alignment: alignment, spacing: 3) {
            ForEach(lines, id: \.self) { Text($0) }
        }
        .font(.footnote)
        .monospacedDigit()
        .foregroundStyle(Color.textSecondary)
        .multilineTextAlignment(alignment == .trailing ? .trailing : .leading)
        .frame(maxWidth: .infinity, alignment: alignment == .trailing ? .trailing : .leading)
    }
}

extension [MatchEvent] {
    /// "Hinshelwood 23', 67'", "Sánchez 82' (OG)", "Salah 45+1' (P)": one line per scorer, in order of their first goal;
    /// an own goal is listed with the side it counted for, which is the event's side.
    func scorerLines(side: String) -> [String] {
        var order: [String] = []
        var minutes: [String: [String]] = [:]
        for event in self where event.side == side && (event.type == "goal" || event.type == "own_goal") {
            let name = event.player.map { $0.split(separator: " ").last.map(String.init) ?? $0 } ?? "—"
            if minutes[name] == nil { order.append(name) }
            let mark = event.type == "own_goal" ? " (OG)" : event.note == "Penalty" ? " (P)" : ""
            minutes[name, default: []].append(event.minuteText + mark)
        }
        return order.map { "\($0) " + minutes[$0]!.joined(separator: ", ") }
    }
}

/// "Premier League · Matchday 7" above the header card.
private struct CompetitionLine: View {
    let match: Match

    var body: some View {
        let ref = match.competition
        // opens the competition in this match's season
        NavigationLink(value: Route.competition(Competition(slug: ref.slug, name: ref.name, kind: ref.kind ?? "league",
                                                            currentSeason: nil, logoUrl: ref.logoUrl),
                                                season: match.season)) {
            HStack(spacing: 8) {
                Logo(url: ref.logoUrl, size: 20, label: ref.name)
                    .accessibilityHidden(true)
                Text(match.round.isEmpty ? ref.name : "\(ref.name) · \(roundTitle(match.round))")
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(Color.textSecondary)
                    .lineLimit(1)
                Image(systemName: "chevron.right")
                    .font(.footnote.weight(.semibold))
                    .foregroundStyle(Color.textTertiary)
                    .accessibilityHidden(true)
            }
            .padding(.horizontal, 4)  // like the section titles above the other cards
            .frame(maxWidth: .infinity, minHeight: 44, alignment: .leading)
            .contentShape(Rectangle())
            .accessibilityElement(children: .combine)
        }
        .buttonStyle(.plain)
    }
}

private struct MatchHeader: View {
    let match: Match
    let events: [MatchEvent]

    var body: some View {
        VStack(spacing: 14) {
            HStack(alignment: .top, spacing: 8) {
                side(match.home)
                VStack(spacing: 4) {
                    // before the start, the kick-off time takes the score's place
                    Text(match.homeScore.map { "\($0) – \(match.awayScore ?? 0)" }
                         ?? (match.status == .notStarted ? match.kickoff.formatted(.dateTime.hour().minute().locale(.app)) : "–"))
                        .font(.digits(48, relativeTo: .largeTitle))
                        .monospacedDigit()
                        .foregroundStyle(Color.textPrimary)
                    if match.status == .live {
                        MatchStatusText(match: match)
                    } else {
                        VStack(spacing: 2) {
                            if match.status != .notStarted { Text(match.status == .finished ? "FT" : "Cancelled") }
                            Text(match.status == .notStarted ? upcomingDay : when).lineLimit(1).minimumScaleFactor(0.8)
                        }
                        .font(.footnote.weight(.medium))
                        .foregroundStyle(Color.textSecondary)
                    }
                }
                .frame(minWidth: 110)
                side(match.away)
            }
            if match.status == .finished, !events.scorerLines(side: "home").isEmpty || !events.scorerLines(side: "away").isEmpty {
                Scorers(events: events)
            }
        }
        .padding(16)
        .frame(maxWidth: .infinity)
        .glassCard()
        // a goal while the match is open (live matches reload every 15 s); not when one is taken back
        .sensoryFeedback(.impact(weight: .medium), trigger: (match.homeScore ?? 0) + (match.awayScore ?? 0)) { old, new in
            new > old
        }
    }

    /// "Today", "Tomorrow", "16 Oct", "16 Oct 2027": the day under an upcoming match's kick-off time.
    private var upcomingDay: String {
        Calendar.current.isDate(match.kickoff, equalTo: .now, toGranularity: .year)
            ? match.dayName : match.kickoff.formatted(.dateTime.day().month(.abbreviated).year().locale(.app))
    }

    /// "18 Oct 21:00": the date and time always show, the year when it isn't this one.
    private var when: String {
        var date = Date.FormatStyle.dateTime.day().month().locale(.app)
        if !Calendar.current.isDate(match.kickoff, equalTo: .now, toGranularity: .year) { date = date.year() }
        return match.kickoff.formatted(date) + " " + match.kickoff.formatted(.dateTime.hour().minute().locale(.app))
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
                if let id = events[index].playerId {
                    NavigationLink(value: Route.player(id)) { EventRow(event: events[index]) }.buttonStyle(.plain)
                } else {
                    EventRow(event: events[index])
                }
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
        .contentShape(Rectangle())
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
