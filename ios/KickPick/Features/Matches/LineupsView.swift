import SwiftUI

/// Lineups tab: both starting XIs on one pitch, then substitutes, coaches and absentees (spec §4.2).
struct LineupsView: View {
    let match: Match
    let lineups: Lineups
    @State private var bench: Int?  // team id; nil: the first side with substitutes

    var body: some View {
        VStack(spacing: 24) {
            if lineups.hasStarters {
                CardSection(title: lineups.title) {
                    TeamHeader(team: match.home, formation: lineups.home?.formation)
                    Pitch(home: lineups.home?.starters ?? [], away: lineups.away?.starters ?? [])
                    TeamHeader(team: match.away, formation: lineups.away?.formation)
                }
            } else {
                EmptyState(text: "No lineups yet")  // FotMob may list who's out before any lineup
            }
            let benches = sides.filter { !$0.lineup.subs.isEmpty }
            if let first = benches.first {
                let shown = benches.first { $0.team.id == bench } ?? first
                VStack(alignment: .leading, spacing: 12) {
                    SectionTitle(benches.count > 1 ? "Substitutes" : "Substitutes · \(first.team.name)")
                    if benches.count > 1 {  // one side at a time, picked like any other tab
                        SegmentedPicker(options: benches.map { ($0.team.id, $0.team.name) },
                                        selection: Binding(get: { shown.team.id }, set: { bench = $0 }), scrolls: true)
                    }
                    VStack(spacing: 0) { Rows(items: shown.lineup.subs) { SubRow(player: $0) } }.glassCard()
                }
            }
            if !coaches.isEmpty {
                CardSection(title: "Coaches") { Rows(items: coaches) { PersonRow(person: $0) } }
            }
            if !absent.isEmpty {
                CardSection(title: "Unavailable") { Rows(items: absent) { PersonRow(person: $0) } }
            }
        }
    }

    private var sides: [Side] {
        [lineups.home.map { Side(team: match.home, lineup: $0) }, lineups.away.map { Side(team: match.away, lineup: $0) }]
            .compactMap { $0 }
    }

    private var coaches: [Person] {
        sides.compactMap { side in side.lineup.coach.map { Person(player: $0, team: side.team, detail: nil) } }
    }

    private var absent: [Person] {
        sides.flatMap { side in side.lineup.unavailable.map { Person(player: $0.player, team: side.team, detail: $0.detail) } }
    }
}

/// Where a starter stands on the drawn pitch. Home plays down from the top, away up from the bottom, mirrored
/// left-right so both read from the viewer's side.
enum PitchLayout {
    static let inset: CGFloat = 30   // half a player cell: keeps goalkeepers inside the card
    static let midGap: CGFloat = 30  // keeps the two front lines apart
    /// FotMob's y runs from about 0.10 (keeper) to 0.87 (front line); that span fills the half, so lines
    /// (≈ 0.19 apart) stay a full player cell apart.
    static let depthRange = 0.10...0.87

    static func point(x: Double, y: Double, home: Bool, in size: CGSize) -> CGPoint {
        let t = min(max((y - depthRange.lowerBound) / (depthRange.upperBound - depthRange.lowerBound), 0), 1)
        let depth = CGFloat(t) * (size.height / 2 - inset - midGap)
        return home ? CGPoint(x: CGFloat(x) * size.width, y: inset + depth)
                    : CGPoint(x: CGFloat(1 - x) * size.width, y: size.height - inset - depth)
    }
}

private struct Side: Identifiable {
    let team: TeamRef
    let lineup: TeamLineup
    var id: Int { team.id }
}

private struct Person: Identifiable {
    let player: PlayerRef
    let team: TeamRef
    let detail: String?
    var id: Int { player.id }
}

private extension Absence {
    /// "Injured · Mid September 2026"
    var detail: String {
        let reasons = ["injury": "Injured", "suspension": "Suspended", "internationalDuty": "International duty"]
        let text = reasons[reason ?? ""] ?? "Unavailable"
        return expectedReturn.map { "\(text) · \($0)" } ?? text
    }
}

private struct TeamHeader: View {
    let team: TeamRef
    let formation: String?

    var body: some View {
        HStack(spacing: 10) {
            Logo(url: team.logoUrl, size: 24, label: team.name)
            Text(team.name).font(.subheadline.weight(.semibold)).foregroundStyle(Color.textPrimary).lineLimit(1)
            Spacer()
            if let formation {
                Text(formation).font(.digits(17, relativeTo: .body, bold: false)).foregroundStyle(Color.textSecondary)
            }
        }
        .padding(.horizontal, 16)
        .frame(minHeight: 48)
        .accessibilityElement(children: .combine)
    }
}

private struct Pitch: View {
    let home: [LineupPlayer]
    let away: [LineupPlayer]

    var body: some View {
        GeometryReader { geo in
            ZStack {
                PitchMarkings()
                ForEach(home) { player in
                    PitchPlayer(player: player)
                        .position(PitchLayout.point(x: player.x ?? 0.5, y: player.y ?? 0.5, home: true, in: geo.size))
                }
                ForEach(away) { player in
                    PitchPlayer(player: player)
                        .position(PitchLayout.point(x: player.x ?? 0.5, y: player.y ?? 0.5, home: false, in: geo.size))
                }
            }
        }
        .aspectRatio(9.0 / 16.0, contentMode: .fit)
        .padding(.horizontal, 8)
    }
}

private struct PitchPlayer: View {
    let player: LineupPlayer

    var body: some View {
        NavigationLink(value: Route.player(player.player.id)) {
            VStack(spacing: 1) {
                Logo(url: player.player.photoUrl, size: 28, label: player.player.name, round: true)
                Text(player.player.name.split(separator: " ").last.map(String.init) ?? player.player.name)
                    .font(.caption2.weight(.semibold))
                    .foregroundStyle(Color.textPrimary)
                    .lineLimit(1)
                    .minimumScaleFactor(0.8)
                HStack(spacing: 3) {
                    Text(player.rating.map { String(format: "%.1f", $0) } ?? " ")  // " " keeps every cell the same height
                        .font(.digits(11, relativeTo: .caption2))
                        .foregroundStyle(player.rating.map(Color.rating) ?? Color.textSecondary)
                    Contributions(goals: player.goals ?? 0, assists: player.assists ?? 0, size: 9)
                }
            }
            .frame(width: 64)
            .contentShape(Rectangle())
            .accessibilityElement(children: .ignore)
            .accessibilityLabel(
                ([player.player.name, player.rating.map { String(format: "rating %.1f", $0) },
                  Contributions.spoken(goals: player.goals ?? 0, assists: player.assists ?? 0)] as [String?])
                    .compactMap { $0 }.filter { !$0.isEmpty }.joined(separator: ", "))
        }
        .buttonStyle(.plain)
    }
}

private struct SubRow: View {
    let player: LineupPlayer

    var body: some View {
        NavigationLink(value: Route.player(player.player.id)) {
            HStack(spacing: 12) {
                Logo(url: player.player.photoUrl, size: 32, label: player.player.name, round: true)
                Text(player.player.name).font(.body).foregroundStyle(Color.textPrimary).lineLimit(1)
                Spacer()
                Contributions(goals: player.goals ?? 0, assists: player.assists ?? 0)
                if let minute = player.subIn {
                    Image(systemName: "arrow.up").font(.footnote.weight(.semibold)).foregroundStyle(Color.textSecondary)
                    Text("\(minute)'").font(.digits(17, relativeTo: .body, bold: false)).foregroundStyle(Color.textSecondary)
                }
                if let flag = player.flagUrl {  // where he's from, rather than the shirt number
                    Logo(url: flag, size: 24, label: "Country").accessibilityHidden(true)
                }
            }
            .padding(.horizontal, 16)
            .frame(minHeight: 48)
            .contentShape(Rectangle())
            .accessibilityElement(children: .ignore)
            .accessibilityLabel(
                ([player.player.name, player.subIn.map { "came on at \($0) minutes" },
                  Contributions.spoken(goals: player.goals ?? 0, assists: player.assists ?? 0)] as [String?])
                    .compactMap { $0 }.filter { !$0.isEmpty }.joined(separator: ", "))
        }
        .buttonStyle(.plain)
    }
}

private struct PersonRow: View {
    let person: Person

    var body: some View {
        NavigationLink(value: Route.player(person.player.id)) {
            HStack(spacing: 12) {
                Logo(url: person.player.photoUrl, size: 32, label: person.player.name, round: true)
                VStack(alignment: .leading, spacing: 2) {
                    Text(person.player.name).font(.body).foregroundStyle(Color.textPrimary).lineLimit(1)
                    if let detail = person.detail {
                        Text(detail).font(.footnote).foregroundStyle(Color.textSecondary).lineLimit(1)
                    }
                }
                Spacer()
                Logo(url: person.team.logoUrl, size: 20, label: person.team.name)
            }
            .padding(.horizontal, 16)
            .padding(.vertical, 8)
            .frame(minHeight: 48)
            .contentShape(Rectangle())
            .accessibilityElement(children: .combine)
        }
        .buttonStyle(.plain)
    }
}
