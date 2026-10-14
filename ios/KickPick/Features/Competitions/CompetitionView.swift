import SwiftUI

struct CompetitionView: View {
    let competition: Competition
    @State private var tab = Tab.table
    @State private var season: String?
    @State private var seasons: [String] = []

    enum Tab: Hashable { case table, matches, bracket }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                SegmentedPicker(options: tabs, selection: $tab)
                switch tab {
                case .table:
                    Loader(id: season) { try await APIClient.shared.standings(competition.slug, season: season) } content: { groups in
                        if groups.isEmpty {
                            EmptyState(text: "Таблицы нет")
                        } else {
                            ForEach(groups, id: \.group) { StandingsCard(group: $0) }
                        }
                    }
                case .matches:
                    Loader(id: season, live: { $0.contains { $0.needsPolling } }) {
                        try await APIClient.shared.matches(competition.slug, season: season)
                    } content: { matches in
                        LazyVStack(alignment: .leading, spacing: 16) {
                            // shortcut: a long season renders from round 1; scroll to the current round if it gets annoying
                            ForEach(matches.grouped(by: \.round)) { group in
                                CardSection(title: roundTitle(group.key)) {
                                    Rows(items: group.items) { match in
                                        NavigationLink(value: Route.match(match.id)) { MatchRow(match: match, showDate: true) }
                                            .buttonStyle(.plain)
                                    }
                                }
                            }
                        }
                    }
                case .bracket:
                    Loader(id: season) { try await APIClient.shared.bracket(competition.slug, season: season) } content: { bracket in
                        if let bracket { BracketView(bracket: bracket) } else { EmptyState(text: "Сетки пока нет") }
                    }
                }
            }
            .padding(16)
        }
        .screen()
        .navigationTitle(competition.name)
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            if !seasons.isEmpty {
                GlassToolbarItem(placement: .topBarTrailing) {
                    Menu {
                        Picker("Сезон", selection: $season) {
                            ForEach(seasons, id: \.self) { Text($0).tag(Optional($0)) }
                        }
                    } label: {
                        Text(season ?? competition.currentSeason ?? "Сезон").font(.subheadline.weight(.semibold))
                    }
                    .menuStyle(.button)
                    .buttonStyle(.glass)
                    .accessibilityLabel("Сезон")
                }
            }
        }
        .task { seasons = (try? await APIClient.shared.seasons(competition.slug)) ?? [] }
    }

    private var tabs: [(value: Tab, title: String)] {
        competition.kind == "league"
            ? [(.table, "Таблица"), (.matches, "Матчи")]
            : [(.table, "Таблица"), (.matches, "Матчи"), (.bracket, "Сетка")]
    }
}
