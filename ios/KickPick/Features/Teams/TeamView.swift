import SwiftUI

struct TeamView: View {
    let id: Int
    private static let positions = ["Coach": "Тренер", "GK": "Вратари", "DF": "Защитники",
                                    "MF": "Полузащитники", "FW": "Нападающие"]

    var body: some View {
        ScrollView {
            Loader { try await APIClient.shared.team(id) } content: { team in
                VStack(alignment: .leading, spacing: 24) {
                    VStack(spacing: 12) {
                        Logo(url: team.logoUrl, size: 72, label: team.name)
                        Text(team.name).font(.title2.weight(.bold).width(.condensed)).foregroundStyle(Color.textPrimary)
                    }
                    .frame(maxWidth: .infinity)
                    if !team.last.isEmpty { matches("Последние матчи", team.last) }
                    if !team.next.isEmpty { matches("Ближайшие", team.next) }
                    ForEach(team.squad.grouped(by: \.position)) { group in
                        CardSection(title: Self.positions[group.key] ?? group.key) {
                            Rows(items: group.items) { entry in
                                NavigationLink(value: Route.player(entry.player.id)) { SquadRow(entry: entry) }
                                    .buttonStyle(.plain)
                            }
                        }
                    }
                }
                .navigationTitle(team.name)
            }
            .padding(16)
        }
        .screen()
        .navigationBarTitleDisplayMode(.inline)
    }

    private func matches(_ title: String, _ items: [Match]) -> some View {
        CardSection(title: title) {
            Rows(items: items) { match in
                NavigationLink(value: Route.match(match.id)) { MatchRow(match: match, showDate: true) }.buttonStyle(.plain)
            }
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
