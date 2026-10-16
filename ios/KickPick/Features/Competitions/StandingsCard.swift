import SwiftUI

struct StandingsCard: View {
    let group: StandingGroup
    var highlight: Int?  // team id whose row stands out (on that team's own page)

    private var title: String? {
        let g = group.group
        if g.isEmpty { return nil }
        if g.count == 1 { return "Group \(g)" }
        return g.hasPrefix("Best 3rd") ? "Best third-placed teams" : g
    }

    var body: some View {
        CardSection(title: title) {
            HStack(spacing: 8) {
                Text("#").frame(width: 24, alignment: .leading)
                Text("Team")
                Spacer()
                Text("P").frame(width: 28)
                Text("GD").frame(width: 36)
                Text("Pts").frame(width: 32)
            }
            .font(.footnote.weight(.medium))
            .foregroundStyle(Color.textTertiary)
            .padding(.horizontal, 16)
            .padding(.top, 12)
            .padding(.bottom, 4)
            .accessibilityHidden(true)
            Rows(items: group.rows) { row in
                let zone = group.legend?.first { $0.color == row.zoneColor }?.title
                if row.team.id == highlight {
                    StandingLine(row: row, zone: zone, highlighted: true)  // already on its page
                } else {
                    NavigationLink(value: Route.team(row.team.id)) { StandingLine(row: row, zone: zone) }.buttonStyle(.plain)
                }
            }
        }
    }
}

private struct StandingLine: View {
    let row: StandingRow
    var zone: String?  // spoken: "Champions League"
    var highlighted = false

    var body: some View {
        let difference = row.goalsFor - row.goalsAgainst
        HStack(spacing: 8) {
            Text("\(row.position)").font(.digits(17, relativeTo: .body, bold: false))
                .foregroundStyle(Color.textSecondary).frame(width: 24, alignment: .leading)
            Logo(url: row.team.logoUrl, size: 24, label: row.team.name)
            Text(row.team.name).font(.body.weight(highlighted ? .semibold : .regular))
                .foregroundStyle(Color.textPrimary).lineLimit(1)
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
        .background(highlighted ? Color.rowHighlight : .clear)
        .overlay(alignment: .leading) {  // the zone: a thin bar at the card's edge, explained by the legend below
            if let color = row.zoneColor.flatMap(Color.init(hex:)) {
                Capsule().fill(color).frame(width: 3).padding(.vertical, 10).padding(.leading, 6)
            }
        }
        .contentShape(Rectangle())
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("\(row.position) place, \(row.team.name), \(row.played) played, \(row.points) points"
                            + (zone.map { ", \($0)" } ?? ""))
    }
}

/// Under the tables: each zone colour and what it means.
struct ZoneLegend: View {
    let zones: [Zone]

    var body: some View {
        if !zones.isEmpty {
            VStack(alignment: .leading, spacing: 8) {
                ForEach(zones, id: \.color) { zone in
                    HStack(spacing: 10) {
                        Capsule().fill(Color(hex: zone.color) ?? .textTertiary).frame(width: 3, height: 14)
                        Text(zone.title).font(.footnote).foregroundStyle(Color.textSecondary)
                    }
                }
            }
            .padding(.horizontal, 4)
            .frame(maxWidth: .infinity, alignment: .leading)
            .accessibilityElement(children: .ignore)
            .accessibilityLabel("Table colours: " + zones.map(\.title).joined(separator: ", "))
        }
    }
}
