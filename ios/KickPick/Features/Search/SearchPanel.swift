import SwiftUI

/// Root screen chrome: the expanding search pinned to the top and the page under it.
/// Content scrolls beneath the glass bar; while searching the page is dimmed.
struct SearchableScreen<Content: View>: View {
    @ViewBuilder let content: Content
    @State private var searching = false

    var body: some View {
        GeometryReader { geo in
            ZStack(alignment: .top) {
                ScrollView {
                    VStack(alignment: .leading, spacing: 24) {  // controls → content (design.md §5)
                        content
                    }
                    .padding(16)
                    .padding(.top, SearchPanel.collapsedHeight + 8)
                }
                // content fades out under the bar and never shows behind the status bar
                .mask {
                    VStack(spacing: 0) {
                        LinearGradient(colors: [.clear, .black], startPoint: .top, endPoint: .bottom)
                            .frame(height: SearchPanel.collapsedHeight + 16)
                        Color.black.ignoresSafeArea(edges: .bottom)  // still scrolls under the floating tab bar
                    }
                }
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
        .onDisappear { searching = false }  // a result was opened or the tab changed
    }
}

/// A glass search field that grows into a card of suggestions: competitions, teams, matches, players.
struct SearchPanel: View {
    static let collapsedHeight: CGFloat = 48
    private static let examples = ["Barcelona", "Haaland", "Real Madrid Barcelona"]

    @Binding var expanded: Bool
    let maxHeight: CGFloat
    @State private var query = ""
    @State private var results: SearchResults?
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
            if expanded {
                Button("Cancel") { expanded = false }
                    .font(.body)
                    .foregroundStyle(Color.textPrimary)
                    .frame(minHeight: Self.collapsedHeight)
                    .transition(reduceMotion ? .opacity : .move(edge: .trailing).combined(with: .opacity))
            }
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
        }
        .padding(.horizontal, 16)
        .frame(height: Self.collapsedHeight)
    }

    @ViewBuilder private var suggestions: some View {
        VStack(alignment: .leading, spacing: 0) {
            if query.trimmingCharacters(in: .whitespaces).count < 2 {
                sectionTitle("Try")
                ForEach(Array(Self.examples.enumerated()), id: \.offset) { index, example in
                    if index > 0 { Hairline() }
                    Button { query = example } label: {
                        HStack(spacing: 12) {
                            Image(systemName: "magnifyingglass").foregroundStyle(Color.textTertiary).accessibilityHidden(true)
                            Text(example).foregroundStyle(Color.textPrimary)
                            Spacer()
                        }
                        .padding(.horizontal, 16)
                        .frame(minHeight: 44)
                        .contentShape(Rectangle())
                    }
                    .buttonStyle(.plain)
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
                            NavigationLink(value: Route.match(match.id)) { MatchRow(match: match, showDate: true) }
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
                ProgressView().frame(maxWidth: .infinity, minHeight: 88)
            }
        }
        .padding(.bottom, 8)
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
