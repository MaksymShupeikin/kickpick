import SwiftUI

struct CompetitionsView: View {
    private struct Kind: Hashable { let kind: String; let title: String }
    private static let kinds = [Kind(kind: "cup", title: "European Cups"), Kind(kind: "league", title: "Leagues"),
                                Kind(kind: "international", title: "International")]

    var body: some View {
        SearchableScreen {
            Loader(skeleton: AnyView(VStack(spacing: 24) {
                ForEach(0..<2, id: \.self) { _ in SkeletonCard(rows: 4) { SkeletonRow(image: 40, lines: 2, trailing: false) } }
            }.shimmer())) { try await APIClient.shared.competitions() } content: { competitions in
                VStack(alignment: .leading, spacing: 24) {
                    ForEach(Self.kinds, id: \.kind) { kind in
                        let items = competitions.filter { $0.kind == kind.kind }
                        if !items.isEmpty {
                            CardSection(title: kind.title) {
                                Rows(items: items) { competition in
                                    NavigationLink(value: Route.competition(competition)) {
                                        CompetitionRow(competition: competition)
                                    }
                                    .buttonStyle(.plain)
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}

struct CompetitionRow: View {
    let competition: Competition

    var body: some View {
        HStack(spacing: 12) {
            Logo(url: competition.logoUrl, size: 40, label: competition.name)
            VStack(alignment: .leading, spacing: 2) {
                Text(competition.name).font(.body).foregroundStyle(Color.textPrimary)
                if let season = competition.currentSeason {
                    Text(season).font(.subheadline).foregroundStyle(Color.textSecondary)
                }
            }
            Spacer()
            Image(systemName: "chevron.right").font(.footnote.weight(.semibold)).foregroundStyle(Color.textTertiary)
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 10)
        .contentShape(Rectangle())
        .accessibilityElement(children: .combine)
    }
}
