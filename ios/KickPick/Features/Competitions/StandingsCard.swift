import SwiftUI

struct StandingsCard: View {
    let group: StandingGroup

    private var title: String? {
        let g = group.group
        if g.isEmpty { return nil }
        if g.count == 1 { return "Группа \(g)" }
        return g.hasPrefix("Best 3rd") ? "Лучшие третьи места" : g
    }

    var body: some View {
        CardSection(title: title) {
            HStack(spacing: 8) {
                Text("#").frame(width: 24, alignment: .leading)
                Text("Команда")
                Spacer()
                Text("И").frame(width: 28)
                Text("Р").frame(width: 36)
                Text("О").frame(width: 32)
            }
            .font(.footnote.weight(.medium))
            .foregroundStyle(Color.textTertiary)
            .padding(.horizontal, 16)
            .padding(.top, 12)
            .padding(.bottom, 4)
            .accessibilityHidden(true)
            Rows(items: group.rows) { row in
                NavigationLink(value: Route.team(row.team.id)) { StandingLine(row: row) }.buttonStyle(.plain)
            }
        }
    }
}

private struct StandingLine: View {
    let row: StandingRow

    var body: some View {
        let difference = row.goalsFor - row.goalsAgainst
        HStack(spacing: 8) {
            Text("\(row.position)").font(.digits(17, relativeTo: .body, bold: false))
                .foregroundStyle(Color.textSecondary).frame(width: 24, alignment: .leading)
            Logo(url: row.team.logoUrl, size: 24, label: row.team.name)
            Text(row.team.name).font(.body).foregroundStyle(Color.textPrimary).lineLimit(1)
            Spacer(minLength: 4)
            Text("\(row.played)").font(.digits(17, relativeTo: .body, bold: false))
                .foregroundStyle(Color.textSecondary).frame(width: 28)
            Text(difference > 0 ? "+\(difference)" : "\(difference)").font(.digits(17, relativeTo: .body, bold: false))
                .foregroundStyle(Color.textSecondary).frame(width: 36)
            Text("\(row.points)").font(.digits(17, relativeTo: .body))
                .foregroundStyle(Color.textPrimary).frame(width: 32)
        }
        .monospacedDigit()
        .frame(minHeight: 44)
        .padding(.horizontal, 16)
        .contentShape(Rectangle())
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("\(row.position) место, \(row.team.name), \(row.played) игр, \(row.points) очков")
    }
}
