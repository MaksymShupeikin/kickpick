import SwiftUI

/// Root screen chrome: the expanding search pinned to the top, an optional header fixed under it (the date strip),
/// and the page scrolling beneath both; while searching the page is dimmed.
struct SearchableScreen<Header: View, Content: View>: View {
    let header: Header
    let content: Content
    @State private var searching = false
    @State private var headerHeight: CGFloat = 0
    @Environment(\.tabBarHeight) private var tabBarHeight
    @Environment(\.searchOpened) private var searchOpened

    init(@ViewBuilder header: () -> Header, @ViewBuilder content: () -> Content) {
        self.header = header()
        self.content = content()
    }

    /// Where the list starts: under the search field, and under the header with 16 above it and 24 below
    /// (search → controls 16, controls → content 24, design.md §5).
    private var top: CGFloat {
        SearchPanel.collapsedHeight + 8 + (headerHeight > 0 ? 16 + headerHeight + 8 : 0)
    }

    var body: some View {
        GeometryReader { geo in
            ZStack(alignment: .top) {
                ScrollView {
                    VStack(alignment: .leading, spacing: 24) {  // controls → content (design.md §5)
                        content
                    }
                    .padding(16)
                    .padding(.top, top)
                    .padding(.bottom, tabBarHeight)  // the list ends above the tab bar, not under it
                }
                // content is hidden behind the search field (and the header) and fades out over 16 pt just below
                // them; at the bottom it fades under the tab bar; never behind the status bar or the home indicator.
                // Each fade covers only the list's padding, so at either end of the list nothing is faded
                .mask {
                    VStack(spacing: 0) {
                        Color.clear.frame(height: max(top - 8, 0))
                        LinearGradient(colors: [.clear, .black], startPoint: .top, endPoint: .bottom)
                            .frame(height: 16)
                        Color.black
                        LinearGradient(colors: [.black, .clear], startPoint: .top, endPoint: .bottom)
                            .frame(height: tabBarHeight + 16)
                    }
                }
                header  // fixed: the list scrolls under it
                    .onGeometryChange(for: CGFloat.self) { $0.size.height } action: { headerHeight = $0 }
                    .padding(.horizontal, 16)
                    .padding(.top, 8 + SearchPanel.collapsedHeight + 16)
                if searching {
                    Color.black.opacity(0.4)
                        .ignoresSafeArea()
                        .onTapGesture { searching = false }
                        .transition(.opacity)
                        .accessibilityHidden(true)
                }
                SearchPanel(expanded: $searching, maxHeight: max(geo.size.height - SearchPanel.collapsedHeight - 40, 160))
                    .padding(.horizontal, 16)
                    .padding(.top, 8)
            }
        }
        .screen()
        .toolbar(.hidden, for: .navigationBar)
        .onDisappear {  // a result was opened or the tab changed
            searching = false
            searchOpened(false)  // said outright: onChange may not run for a view that's gone, and the bar would stay hidden
        }
        .onChange(of: searching) { _, open in searchOpened(open) }
    }
}

extension SearchableScreen where Header == EmptyView {
    init(@ViewBuilder content: () -> Content) {
        self.init(header: { EmptyView() }, content: content)
    }
}

/// A glass search field that grows into a card of suggestions: competitions, teams, matches, players.
struct SearchPanel: View {
    static let collapsedHeight: CGFloat = 48

    @Binding var expanded: Bool
    let maxHeight: CGFloat
    @State private var query = ""
    @State private var results: SearchResults?
    @State private var latest: SearchSuggestions?
    @State private var contentHeight: CGFloat = 0
    @FocusState private var focused: Bool
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    var body: some View {
        let shape = RoundedRectangle(cornerRadius: expanded ? 20 : Self.collapsedHeight / 2, style: .continuous)
        HStack(alignment: .top, spacing: 12) {
            VStack(spacing: 0) {
                field
                if expanded {
                    Hairline()
                    ScrollView {
                        suggestions.background(GeometryReader { geo in
                            Color.clear
                                .onAppear { contentHeight = geo.size.height }
                                .onChange(of: geo.size.height) { _, height in contentHeight = height }
                        })
                    }
                    .frame(height: min(contentHeight, maxHeight))
                    .animation(reduceMotion ? nil : .easeInOut(duration: 0.2), value: contentHeight)
                    .transition(reduceMotion ? .opacity : .opacity.combined(with: .move(edge: .top)))
                }
            }
            .clipShape(shape)
            .background(GlassBackground(shape: shape))
        }
        .animation(.easeInOut(duration: reduceMotion ? 0.15 : 0.25), value: expanded)
        .onChange(of: focused) { _, isFocused in if isFocused { expanded = true } }
        .onChange(of: expanded) { _, isExpanded in
            if !isExpanded {
                focused = false
                query = ""
                results = nil
            }
        }
                .task(id: query) {
            let text = query.trimmingCharacters(in: .whitespaces)
            guard text.count >= 2 else { results = nil; return }
            try? await Task.sleep(for: .milliseconds(300))
            guard !Task.isCancelled else { return }
            if let found = try? await APIClient.shared.search(text) { results = found }
        }
        .task(id: expanded) {  // fresh picks each time the panel opens
            guard expanded else { return }
            latest = (try? await APIClient.shared.searchSuggestions()) ?? SearchSuggestions(match: nil, team: nil, player: nil)
        }
        .accessibilityAction(.escape) { expanded = false }
    }

    private var field: some View {
        HStack(spacing: 10) {
            Image(systemName: "magnifyingglass").foregroundStyle(Color.textSecondary).accessibilityHidden(true)
            TextField("", text: $query, prompt: Text("Team, player or match").foregroundStyle(Color.textTertiary))
                .focused($focused)
                .submitLabel(.search)
                .autocorrectionDisabled()
                .textInputAutocapitalization(.never)
                .foregroundStyle(Color.textPrimary)
                .accessibilityLabel("Search")
            if !query.isEmpty {
                Button { query = "" } label: { Image(systemName: "xmark.circle.fill") }
                    .foregroundStyle(Color.textTertiary)
                    .accessibilityLabel("Clear")
            }
            if expanded {  // closing lives in the card, so the open panel keeps the full width
                Button { expanded = false } label: {
                    Image(systemName: "xmark")
                        .font(.body.weight(.semibold))
                        .foregroundStyle(Color.textSecondary)
                        .frame(width: 44, height: 44)
                        .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .accessibilityLabel("Cancel")
                .transition(.opacity)
            }
        }
        .padding(.leading, 16)
        .padding(.trailing, expanded ? 4 : 16)  // the close button brings its own 44-pt tap area
        .frame(height: Self.collapsedHeight)
    }

    @ViewBuilder private var suggestions: some View {
        VStack(alignment: .leading, spacing: 0) {
            if query.trimmingCharacters(in: .whitespaces).count < 2 {
                if let latest {
                    let picks = Pick.all(latest)
                    if picks.isEmpty {
                        Text("Search teams, players and matches")
                            .font(.subheadline)
                            .foregroundStyle(Color.textTertiary)
                            .frame(maxWidth: .infinity, minHeight: 88)
                    } else {
                        sectionTitle("Latest")
                        Rows(items: picks) { pick($0) }
                            .simultaneousGesture(TapGesture().onEnded { focused = false })  // as for results below
                    }
                } else {  // the latest match, club and player on their way
                    VStack(spacing: 0) { SkeletonMatchRow(); SkeletonRow(image: 40, trailing: false); SkeletonRow(image: 40, lines: 2, trailing: false) }
                        .padding(.top, 8)
                        .shimmer()
                }
            } else if let results {
                Group {
                    if results.isEmpty {
                        Text("Nothing found")
                            .font(.subheadline)
                            .foregroundStyle(Color.textTertiary)
                            .frame(maxWidth: .infinity, minHeight: 88)
                    }
                    if !results.competitions.isEmpty {
                        sectionTitle("Competitions")
                        Rows(items: results.competitions) { competition in
                            NavigationLink(value: Route.competition(competition)) { CompetitionRow(competition: competition) }
                                .buttonStyle(.plain)
                        }
                    }
                    if !results.teams.isEmpty {
                        sectionTitle("Teams")
                        Rows(items: results.teams) { team in
                            NavigationLink(value: Route.team(team.id)) {
                                hit(Logo(url: team.logoUrl, size: 40, label: team.name), team.name, nil)
                            }
                            .buttonStyle(.plain)
                        }
                    }
                    if !results.matches.isEmpty {
                        sectionTitle("Matches")
                        Rows(items: results.matches) { match in
                            NavigationLink(value: Route.match(match.id)) { MatchRow(match: match) }
                                .buttonStyle(.plain)
                        }
                    }
                    if !results.players.isEmpty {
                        sectionTitle("Players")
                        Rows(items: results.players) { player in
                            NavigationLink(value: Route.player(player.id)) {
                                hit(Logo(url: player.photoUrl, size: 40, label: player.name, round: true), player.name, player.teamName)
                            }
                            .buttonStyle(.plain)
                        }
                    }
                }
                // a result is opening: drop focus now, or SwiftUI restores it on the way back and the panel pops open again
                .simultaneousGesture(TapGesture().onEnded { focused = false })
            } else {
                VStack(spacing: 0) { ForEach(0..<3, id: \.self) { _ in SkeletonRow(image: 40, trailing: false) } }
                    .padding(.top, 8)
                    .shimmer()
            }
        }
        .padding(.bottom, 8)
    }

    private enum Pick: Identifiable {
        case match(Match), team(TeamRef), player(PlayerHit)

        var id: String {
            switch self {
            case .match(let m): "m\(m.id)"
            case .team(let t): "t\(t.id)"
            case .player(let p): "p\(p.id)"
            }
        }

        static func all(_ s: SearchSuggestions) -> [Pick] {
            [s.match.map(Pick.match), s.team.map(Pick.team), s.player.map(Pick.player)].compactMap { $0 }
        }
    }

    @ViewBuilder private func pick(_ pick: Pick) -> some View {
        switch pick {
        case .match(let match):
            NavigationLink(value: Route.match(match.id)) { MatchRow(match: match) }.buttonStyle(.plain)
        case .team(let team):
            NavigationLink(value: Route.team(team.id)) {
                hit(Logo(url: team.logoUrl, size: 40, label: team.name), team.name, nil)
            }
            .buttonStyle(.plain)
        case .player(let player):
            NavigationLink(value: Route.player(player.id)) {
                hit(Logo(url: player.photoUrl, size: 40, label: player.name, round: true), player.name, player.teamName)
            }
            .buttonStyle(.plain)
        }
    }

    private func sectionTitle(_ title: String) -> some View {
        Text(title)
            .font(.footnote.weight(.medium))
            .foregroundStyle(Color.textTertiary)
            .padding(.horizontal, 16)
            .padding(.top, 14)
            .padding(.bottom, 4)
            .accessibilityAddTraits(.isHeader)
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
