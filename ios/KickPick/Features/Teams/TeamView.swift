import SwiftUI

struct TeamView: View {
    let id: Int
    @State private var tab = Tab.results
    private static let positions = ["Coach": "Coach", "GK": "Goalkeepers", "DF": "Defenders",
                                    "MF": "Midfielders", "FW": "Forwards"]

    enum Tab: Hashable { case results, fixtures, squad, transfers }

    var body: some View {
        ScrollView {
            Loader { try await APIClient.shared.team(id) } content: { team in
                VStack(spacing: 24) {
                    VStack(spacing: 12) {
                        Logo(url: team.logoUrl, size: 72, label: team.name)
                        Text(team.name)
                            .font(.title2.weight(.bold).width(.condensed))
                            .foregroundStyle(Color.textPrimary)
                            .revealsInBar {
                                HStack(spacing: 8) {
                                    Logo(url: team.logoUrl, size: 20, label: team.name)
                                    Text(team.name).font(.headline.width(.condensed)).foregroundStyle(Color.textPrimary)
                                }
                            }
                    }
                    .frame(maxWidth: .infinity)
                    SegmentedPicker(options: [(.results, "Results"), (.fixtures, "Fixtures"), (.squad, "Squad"),
                                              (.transfers, "Transfers")], selection: $tab)
                    switch tab {
                    case .results: matches(team.last, empty: "No matches")
                    case .fixtures: matches(team.next, empty: "No upcoming matches")
                    case .squad: squad(team.squad)
                    case .transfers: TransfersTab(transfers: team.transfers)
                    }
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
                    NavigationLink(value: Route.match(match.id)) { MatchRow(match: match, showDate: true) }
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
        if let feeEur, feeEur > 0 { return "€" + feeEur.formatted(.number.notation(.compactName).locale(.app)).uppercased() }
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
            if let number = entry.shirtNumber {
                Text("\(number)").font(.digits(17, relativeTo: .body, bold: false)).foregroundStyle(Color.textSecondary)
            }
        }
        .padding(.horizontal, 16)
        .frame(minHeight: 52)
        .contentShape(Rectangle())
        .accessibilityElement(children: .combine)
    }
}
