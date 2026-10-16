import SwiftUI

struct CompetitionView: View {
    let competition: Competition
    @State private var tab = Tab.table
    @State private var season: String?

    init(competition: Competition, season: String? = nil) {
        self.competition = competition
        _season = State(initialValue: season)
    }
    @State private var seasons: [String] = []
    @State private var matchesOpened = 0  // each opening of Matches scrolls to the current round again
    @State private var screenWidth: CGFloat = 0
    @State private var seasonTextWidth: CGFloat = 0

    enum Tab: Hashable { case table, matches, bracket }

    var body: some View {
        ScrollViewReader { proxy in
        ScrollView {
            LazyVStack(alignment: .leading, spacing: 16, pinnedViews: .sectionHeaders) {  // the tabs stick under the bar
                Section {
                    switch tab {
                    case .table:
                        Loader(id: season, skeleton: AnyView(TableSkeleton())) {
                            try await APIClient.shared.standings(competition.slug, season: season)
                        } content: { groups in
                            if groups.isEmpty {
                                EmptyState(text: "No table")
                            } else {
                                // one item for the lazy stack: a short legend beside a tall card as its own item has
                                // the stack re-estimating its height and re-scrolling every frame once scrolled
                                VStack(spacing: 16) {
                                    ForEach(groups, id: \.group) { StandingsCard(group: $0) }
                                    ZoneLegend(zones: Zone.legend(of: groups))
                                }
                            }
                        }
                    case .matches:
                        Loader(id: season, skeleton: AnyView(MatchListSkeleton()), live: { $0.contains { $0.needsPolling } }) {
                            try await APIClient.shared.matches(competition.slug, season: season)
                        } content: { matches in
                            // each round carries a clear strip above its card (spacing pulls the cards back to 16
                            // apart), so scrolling a round to the top leaves its title clear of the pinned tabs
                            LazyVStack(alignment: .leading, spacing: 16 - Self.pinnedTabs) {
                                ForEach(matches.grouped(by: \.round)) { group in
                                    VStack(spacing: 0) {
                                        Color.clear.frame(height: Self.pinnedTabs)
                                        CardSection(title: roundTitle(group.key)) {
                                            Rows(items: group.items) { match in
                                                NavigationLink(value: Route.match(match.id)) { MatchRow(match: match) }
                                                    .buttonStyle(.plain)
                                            }
                                        }
                                    }
                                    .id(group.key)
                                }
                            }
                            .padding(.top, -Self.pinnedTabs)
                            .onGeometryChange(for: Bool.self) { $0.size.height > 0 } action: { laidOut in
                                guard laidOut, let round = matches.currentRound else { return }
                                // a lazy list lands short of a far round on the first try (row heights are estimates
                                // until drawn, and the scroll view may still have the previous tab's height): go again
                                DispatchQueue.main.async { proxy.scrollTo(round, anchor: .top) }
                                DispatchQueue.main.asyncAfter(deadline: .now() + 0.15) { proxy.scrollTo(round, anchor: .top) }
                            }
                            .id(matchesOpened)  // a fresh list on each opening (SwiftUI may keep the old one), so it scrolls again
                        }
                    case .bracket:
                        Loader(id: season) { try await APIClient.shared.bracket(competition.slug, season: season) } content: { bracket in
                            if let bracket { BracketView(bracket: bracket) } else { EmptyState(text: "No bracket yet") }
                        }
                    }
                } header: {
                    SegmentedPicker(options: tabs, selection: $tab).joinsBarWhenPinned()
                }
            }
            .scrollsToTabs(on: "\(tab)|\(season ?? "")")
            .onChange(of: tab) { if tab == .matches { matchesOpened += 1 } }
            .padding(16)
        }
        }
        .onGeometryChange(for: CGFloat.self) { $0.size.width } action: { screenWidth = $0 }
        .background {  // the season label, measured where it is always drawn (the bar may fold the real one away)
            Text(seasonLabel).font(.subheadline.weight(.semibold)).fixedSize().hidden()
                .onGeometryChange(for: CGFloat.self) { $0.size.width } action: { seasonTextWidth = $0 }
        }
        .screen()
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            // right after the back button. Its own width (a leading item is squeezed to "Ch…" otherwise), but no
            // more than the room the season button leaves, or the bar folds that button into "…". The middle slot
            // can't do this: on a wide screen the bar centres it.
            GlassToolbarItem(placement: .topBarLeading) {
                HStack(spacing: 8) {
                    Logo(url: competition.logoUrl, size: 24, label: competition.name).accessibilityHidden(true)
                    Text(competition.name)
                        .font(.headline.width(.condensed))
                        .foregroundStyle(Color.textPrimary)
                        .lineLimit(1)
                }
                .frame(maxWidth: max(screenWidth - seasonTextWidth - Self.barReserve, 60), alignment: .leading)
                .fixedSize()
                .accessibilityElement(children: .combine)
                .accessibilityAddTraits(.isHeader)
            }
            if !seasons.isEmpty {
                GlassToolbarItem(placement: .topBarTrailing) {
                    Menu {
                        Picker("Season", selection: $season) {
                            ForEach(seasons, id: \.self) { Text($0).tag(Optional($0)) }
                        }
                    } label: {
                        Text(seasonLabel).font(.subheadline.weight(.semibold))
                            .lineLimit(1)
                            .fixedSize()  // one line, however wide the title next to it
                    }
                    .menuStyle(.button)
                    .buttonStyle(.glass)
                    .accessibilityLabel("Season")
                    .accessibilityValue(season ?? competition.currentSeason ?? "")
                }
            }
        }
        .task { seasons = (try? await APIClient.shared.seasons(competition.slug)) ?? [] }
        .sensoryFeedback(.selection, trigger: season)
    }

    private static let pinnedTabs: CGFloat = 72  // the pinned tabs' height with a gap below
    /// Bar width the title can't have besides the season text: side margins, the back button, the gaps and the
    /// season button's ~49 pt of padding. Measured on iOS 26 with the whole button: 125 + button folded it into "…",
    /// 150 + button didn't, so ~175 + text is the edge; 182 keeps a margin.
    private static let barReserve: CGFloat = 182

    private var seasonLabel: String { (season ?? competition.currentSeason).map(Self.shortSeason) ?? "Season" }

    /// "2026/2027" → "26/27", "2026/2027 - Apertura" → "26/27 Apertura": the bar's season button stays narrow enough
    /// to leave the title room (the picker's list keeps the full names).
    static func shortSeason(_ season: String) -> String {
        season.replacingOccurrences(of: #"\d{2}(\d{2})/\d{2}(\d{2})"#, with: "$1/$2", options: .regularExpression)
            .replacingOccurrences(of: " - ", with: " ")
    }

    private var tabs: [(value: Tab, title: String)] {
        competition.kind == "league"
            ? [(.table, "Table"), (.matches, "Matches")]
            : [(.table, "Table"), (.matches, "Matches"), (.bracket, "Bracket")]
    }
}
