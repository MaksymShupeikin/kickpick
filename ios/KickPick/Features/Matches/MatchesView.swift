import SwiftUI

struct MatchesView: View {
    @State private var day = Calendar.current.startOfDay(for: .now)
    @State private var pickingDate = false

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                HStack(spacing: 8) {
                    SegmentedPicker(options: relativeDays, selection: $day)
                    Button { pickingDate = true } label: { Image(systemName: "calendar") }
                        .buttonStyle(.glassIcon)
                        .accessibilityLabel("Выбрать дату")
                }
                Loader(id: day, placeholder: Match.placeholders, live: { $0.contains { $0.status == .live } }) {
                    try await APIClient.shared.matches(from: day, to: Calendar.current.date(byAdding: .day, value: 1, to: day)!)
                } content: { matches in
                    if matches.isEmpty {
                        EmptyState(text: "Матчей нет")
                    } else {
                        ForEach(matches.grouped(by: \.competition.slug)) { group in
                            let competition = group.items[0].competition
                            CardSection(title: competition.name, logo: competition.logoUrl) {
                                Rows(items: group.items) { match in
                                    NavigationLink(value: Route.match(match.id)) { MatchRow(match: match) }
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
        .navigationTitle("Матчи")
        .sheet(isPresented: $pickingDate) {
            DatePicker("Дата", selection: Binding(get: { day }, set: {
                day = Calendar.current.startOfDay(for: $0)
                pickingDate = false
            }), displayedComponents: .date)
            .datePickerStyle(.graphical)
            .environment(\.locale, .app)
            .padding()
            .presentationDetents([.medium])
        }
    }

    private var relativeDays: [(value: Date, title: String)] {
        let today = Calendar.current.startOfDay(for: .now)
        return [(-1, "Вчера"), (0, "Сегодня"), (1, "Завтра")].map { offset, title in
            (Calendar.current.date(byAdding: .day, value: offset, to: today)!, title)
        }
    }
}
