import SwiftUI

struct TeamView: View {
    let id: Int
    @State private var tab = Tab.results
    @State private var tableCompetition: String?  // slug; nil: the first (the league)
    private static let positions = ["Coach": "Coach", "GK": "Goalkeepers", "DF": "Defenders",
                                    "MF": "Midfielders", "FW": "Forwards"]

    enum Tab: Hashable { case results, fixtures, table, squad, transfers, trophies }

    var body: some View {
        ScrollView {
            Loader(skeleton: AnyView(ProfileSkeleton(image: 72, facts: 4))) { try await APIClient.shared.team(id) } content: { team in
                VStack(spacing: 24) {  // headers stay out of the lazy stack: their bar items must not unload
                    VStack(spacing: 12) {
                        Logo(url: team.logoUrl, size: 72, label: team.name)
                        VStack(spacing: 0) {
                            Text(team.name)
                                .font(.title2.weight(.bold).width(.condensed))
                                .foregroundStyle(Color.textPrimary)
                                .accessibilityAddTraits(.isHeader)
                                .revealsInBar {
                                    HStack(spacing: 8) {
                                        Logo(url: team.logoUrl, size: 20, label: team.name)
                                        Text(team.name).font(.headline.width(.condensed)).foregroundStyle(Color.textPrimary)
                                    }
                                }
                            if let country = team.country { TeamLink(team: country) }  // opens the national side
                        }
                    }
                    .frame(maxWidth: .infinity)
                    if !team.facts.isEmpty { FactsCard(facts: team.facts) }
                    LazyVStack(spacing: 24, pinnedViews: .sectionHeaders) {  // the tabs stick under the bar
                        Section {
                            switch tab {
                            case .results: matches(team.last, empty: "No matches")
                            case .fixtures: matches(team.next, empty: "No upcoming matches")
                            case .table: TableTab(team: team.id, standings: team.standings, competition: $tableCompetition)
                            case .squad: squad(team.squad)
                            case .transfers: TransfersTab(transfers: team.transfers)
                            case .trophies: TrophiesTab(trophies: team.trophies)
                            }
                        } header: {
                            SegmentedPicker(options: [(.results, "Results"), (.fixtures, "Fixtures"), (.table, "Table"),
                                                      (.squad, "Squad"), (.transfers, "Transfers"), (.trophies, "Trophies")],
                                            selection: $tab, scrolls: true)
                                .joinsBarWhenPinned()
                        }
                    }
                    .scrollsToTabs(on: "\(tab)|\(tableCompetition ?? "")")
                }
            }
            .padding(16)
        }
        .screen()
        .navigationBarTitleDisplayMode(.inline)
    }

    @ViewBuilder private func matches(_ items: [Match], empty: String) -> some View {
        if items.isEmpty {
            EmptyState(text: empty)
        } else {
            CardSection(title: nil) {
                Rows(items: items) { match in
                    NavigationLink(value: Route.match(match.id)) { MatchRow(match: match) }
                        .buttonStyle(.plain)
                }
            }
        }
    }

    @ViewBuilder private func squad(_ entries: [SquadEntry]) -> some View {
        if entries.isEmpty {
            EmptyState(text: "No squad")
        } else {
            VStack(spacing: 24) {
                ForEach(entries.grouped(by: \.position)) { group in
                    CardSection(title: group.key.flatMap { Self.positions[$0] ?? $0 } ?? "Other") {
                        Rows(items: group.items) { entry in
                            NavigationLink(value: Route.player(entry.player.id)) { SquadRow(entry: entry) }
                                .buttonStyle(.plain)
                        }
                    }
                }
            }
        }
    }
}

private struct TransfersTab: View {
    let transfers: Transfers

    var body: some View {
        if transfers.arrivals.isEmpty && transfers.departures.isEmpty {
            EmptyState(text: "No transfers")
        } else {
            VStack(spacing: 24) {
                section("Arrivals", transfers.arrivals, direction: "from")
                section("Departures", transfers.departures, direction: "to")
            }
        }
    }

    @ViewBuilder private func section(_ title: String, _ items: [Transfer], direction: String) -> some View {
        if !items.isEmpty {
            CardSection(title: title) {
                Rows(items: items) { transfer in
                    NavigationLink(value: Route.player(transfer.player.id)) {
                        TransferRow(transfer: transfer, direction: direction)
                    }
                    .buttonStyle(.plain)
                }
            }
        }
    }
}

private struct TransferRow: View {
    let transfer: Transfer
    let direction: String

    var body: some View {
        HStack(spacing: 12) {
            Logo(url: transfer.player.photoUrl, size: 36, label: transfer.player.name, round: true)
            VStack(alignment: .leading, spacing: 2) {
                Text(transfer.player.name).font(.body).foregroundStyle(Color.textPrimary).lineLimit(1)
                Text(subtitle).font(.footnote).foregroundStyle(Color.textSecondary).lineLimit(1)
            }
            Spacer(minLength: 8)
            Text(transfer.feeLabel).font(.subheadline.weight(.semibold)).foregroundStyle(Color.textPrimary)
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 10)
        .contentShape(Rectangle())
        .accessibilityElement(children: .combine)
    }

    /// "from Leeds United · 1 Jul 2026"
    private var subtitle: String {
        let date = transfer.date.formatted(.dateTime.day().month(.abbreviated).year().locale(.app))
        return transfer.team?.name.map { "\(direction) \($0) · \(date)" } ?? date
    }
}

extension Transfer {
    /// "€45M", "Loan", "Free", "Undisclosed" or "—".
    var feeLabel: String {
        if let feeEur, feeEur > 0 { return feeEur.euros }
        if onLoan { return "Loan" }
        switch feeText {
        case "free transfer": return "Free"
        case "undisclosed": return "Undisclosed"
        default: return "—"
        }
    }
}

private struct SquadRow: View {
    let entry: SquadEntry

    var body: some View {
        HStack(spacing: 12) {
            Logo(url: entry.player.photoUrl, size: 36, label: entry.player.name, round: true)
            Text(entry.player.name).font(.body).foregroundStyle(Color.textPrimary).lineLimit(1)
            Spacer()
            if let club = entry.club {  // a national side: where he plays
                Logo(url: club.logoUrl, size: 24, label: club.name ?? "Club")
            } else if let flag = entry.flagUrl {  // a club: where he's from, rather than the shirt number
                Logo(url: flag, size: 24, label: entry.countryName ?? "Country")
            }
        }
        .padding(.horizontal, 16)
        .frame(minHeight: 52)
        .contentShape(Rectangle())
        .accessibilityElement(children: .combine)
    }
}

/// The team's current tables, one tournament at a time, with its own row highlighted.
private struct TableTab: View {
    let team: Int
    let standings: [TeamStandings]
    @Binding var competition: String?  // slug; nil: the first (the league)

    var body: some View {
        if let first = standings.first {
            let shown = standings.first { $0.competition.slug == competition } ?? first
            VStack(spacing: 24) {
                if standings.count > 1 {
                    SegmentedPicker(options: standings.map { ($0.competition.slug, $0.competition.name) },
                                    selection: Binding(get: { shown.competition.slug }, set: { competition = $0 }),
                                    scrolls: true)
                }
                ForEach(shown.groups, id: \.group) { StandingsCard(group: $0, highlight: team) }
                ZoneLegend(zones: Zone.legend(of: shown.groups))
            }
        } else {
            EmptyState(text: "No table")
        }
    }
}

extension Int {
    /// "€45M", "€226M": compact and upper-case (en_GB writes "m").
    var euros: String { "€" + formatted(.number.notation(.compactName).locale(.app)).uppercased() }
}

private extension TeamPage {
    var facts: [Fact] {
        var out: [Fact] = []
        if let venue {
            out.append((label: "Stadium", value: venue.name, flag: nil))
            if let city = venue.city, !city.isEmpty { out.append((label: "City", value: city, flag: nil)) }
            if let capacity = venue.capacity {
                out.append((label: "Capacity", value: capacity.formatted(.number.locale(.app)), flag: nil))
            }
            if let opened = venue.opened { out.append((label: "Opened", value: String(opened), flag: nil)) }
        }
        return out
    }
}

/// Titles and runner-up finishes per competition, most titles first (the API's order).
private struct TrophiesTab: View {
    let trophies: [Trophy]

    var body: some View {
        if trophies.isEmpty {
            EmptyState(text: "No trophies")
        } else {
            CardSection(title: nil) {
                ColumnsHeader(first: "Competition", columns: ["Won", "2nd"])
                Rows(items: trophies) { trophy in
                    StatLine(logo: trophy.competition.logoUrl, title: trophy.competition.name ?? "—",
                             subtitle: trophy.seasonsWon.first.map { "Last won \($0)" },
                             values: [String(trophy.won), String(trophy.runnerUp)])
                }
            }
        }
    }
}
