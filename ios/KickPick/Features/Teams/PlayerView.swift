import SwiftUI

struct PlayerView: View {
    let id: Int

    var body: some View {
        ScrollView {
            Loader { try await APIClient.shared.player(id) } content: { player in
                VStack(spacing: 24) {
                    VStack(spacing: 12) {
                        Logo(url: player.photoUrl, size: 96, label: player.name, round: true)
                        Text(player.name).font(.title2.weight(.bold).width(.condensed)).foregroundStyle(Color.textPrimary)
                    }
                    VStack(spacing: 0) {
                        ForEach(Array(player.facts.enumerated()), id: \.offset) { index, fact in
                            if index > 0 { Hairline() }
                            HStack {
                                Text(fact.label).foregroundStyle(Color.textSecondary)
                                Spacer()
                                Text(fact.value).foregroundStyle(Color.textPrimary)
                            }
                            .font(.body)
                            .padding(.horizontal, 16)
                            .frame(minHeight: 44)
                            .accessibilityElement(children: .combine)
                        }
                    }
                    .glassCard()
                    ForEach(player.teams) { MembershipCard(membership: $0) }
                }
                .navigationTitle(player.name)
            }
            .padding(16)
        }
        .screen()
        .navigationBarTitleDisplayMode(.inline)
    }
}

private extension PlayerPage {
    var facts: [(label: String, value: String)] {
        let positions = ["Coach": "Тренер", "GK": "Вратарь", "DF": "Защитник", "MF": "Полузащитник", "FW": "Нападающий"]
        var out: [(label: String, value: String)] = []
        if let position { out.append((label: "Позиция", value: positions[position] ?? position)) }
        if let birthDate, let born = try? Date(birthDate + "T00:00:00Z", strategy: .iso8601),
           let age = Calendar.current.dateComponents([.year], from: born, to: .now).year {
            out.append((label: "Возраст", value: "\(age)"))
        }
        if let countryCode { out.append((label: "Страна", value: countryCode)) }
        return out
    }
}

private struct MembershipCard: View {
    let membership: Membership

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            NavigationLink(value: Route.team(membership.team.id)) {
                HStack(spacing: 10) {
                    Logo(url: membership.team.logoUrl, size: 24, label: membership.team.name)
                    Text(membership.team.name).font(.body.weight(.semibold)).foregroundStyle(Color.textPrimary)
                    Spacer()
                    if let number = membership.shirtNumber {
                        Text("\(number)").font(.digits(22, relativeTo: .title3)).foregroundStyle(Color.textPrimary)
                            .accessibilityLabel("Номер \(number)")
                    }
                }
            }
            .buttonStyle(.plain)
            HStack {
                stat("Голы", membership.stats.goals.map(String.init))
                stat("Ассисты", membership.stats.assists.map(String.init))
                stat("ЖК", membership.stats.yellowCards.map(String.init))
                stat("КК", membership.stats.redCards.map(String.init))
                stat("Рейтинг", membership.stats.rating.map { String(format: "%.1f", $0) })
            }
        }
        .padding(16)
        .glassCard()
    }

    private func stat(_ label: String, _ value: String?) -> some View {
        VStack(spacing: 4) {
            Text(value ?? "—").font(.digits(22, relativeTo: .title3)).foregroundStyle(Color.textPrimary)
            Text(label).font(.footnote.weight(.medium)).foregroundStyle(Color.textTertiary)
        }
        .frame(maxWidth: .infinity)
        .accessibilityElement(children: .combine)
    }
}
