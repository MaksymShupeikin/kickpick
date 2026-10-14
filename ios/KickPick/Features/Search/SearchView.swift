import SwiftUI

struct SearchView: View {
    @State private var query = ""
    @State private var results: SearchResults?

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 24) {
                if let results {
                    if results.isEmpty { EmptyState(text: "Ничего не найдено") }
                    if !results.competitions.isEmpty {
                        CardSection(title: "Турниры") {
                            Rows(items: results.competitions) { competition in
                                NavigationLink(value: Route.competition(competition)) { CompetitionRow(competition: competition) }
                                    .buttonStyle(.plain)
                            }
                        }
                    }
                    if !results.teams.isEmpty {
                        CardSection(title: "Команды") {
                            Rows(items: results.teams) { team in
                                NavigationLink(value: Route.team(team.id)) {
                                    hit(Logo(url: team.logoUrl, size: 40, label: team.name), team.name, nil)
                                }
                                .buttonStyle(.plain)
                            }
                        }
                    }
                    if !results.players.isEmpty {
                        CardSection(title: "Игроки") {
                            Rows(items: results.players) { player in
                                NavigationLink(value: Route.player(player.id)) {
                                    hit(Logo(url: player.photoUrl, size: 40, label: player.name, round: true), player.name, player.teamName)
                                }
                                .buttonStyle(.plain)
                            }
                        }
                    }
                } else {
                    EmptyState(text: "Команды, игроки, турниры")
                }
            }
            .padding(16)
        }
        .screen()
        .navigationTitle("Поиск")
        // shortcut: FotMob names are Latin, so "Барселона" finds nothing; add Russian aliases if that matters
        .searchable(text: $query, prompt: "Barcelona, Yamal, Champions League")
        .task(id: query) {
            let text = query.trimmingCharacters(in: .whitespaces)
            guard text.count >= 2 else { results = nil; return }
            try? await Task.sleep(for: .milliseconds(300))
            guard !Task.isCancelled else { return }
            if let found = try? await APIClient.shared.search(text) { results = found }
        }
    }

    private func hit(_ image: Logo, _ title: String, _ subtitle: String?) -> some View {
        HStack(spacing: 12) {
            image
            VStack(alignment: .leading, spacing: 2) {
                Text(title).font(.body).foregroundStyle(Color.textPrimary)
                if let subtitle { Text(subtitle).font(.subheadline).foregroundStyle(Color.textSecondary) }
            }
            Spacer()
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 10)
        .contentShape(Rectangle())
        .accessibilityElement(children: .combine)
    }
}
