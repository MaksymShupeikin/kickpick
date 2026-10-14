import SwiftUI

struct CompetitionsView: View {
    private struct Kind: Hashable { let kind: String; let title: String }
    private static let kinds = [Kind(kind: "league", title: "Лиги"), Kind(kind: "cup", title: "Еврокубки"),
                                Kind(kind: "international", title: "Сборные")]

    var body: some View {
        ScrollView {
            Loader { try await APIClient.shared.competitions() } content: { competitions in
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
            .padding(16)
        }
        .screen()
        .navigationTitle("Турниры")
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
