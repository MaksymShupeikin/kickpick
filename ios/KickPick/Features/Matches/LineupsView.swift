import SwiftUI

/// Lineups tab: both starting XIs on one pitch, then substitutes, coaches and absentees (spec §4.2).
struct LineupsView: View {
    let match: Match
    let lineups: Lineups

    var body: some View {
        VStack(spacing: 24) {
            VStack(spacing: 0) {
                TeamHeader(team: match.home, formation: lineups.home?.formation)
                Pitch(home: lineups.home?.starters ?? [], away: lineups.away?.starters ?? [])
                TeamHeader(team: match.away, formation: lineups.away?.formation)
            }
            .glassCard()
            ForEach(sides) { side in
                if !side.lineup.subs.isEmpty {
                    CardSection(title: "Substitutes · \(side.team.name)") {
                        Rows(items: side.lineup.subs) { SubRow(player: $0) }
                    }
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
    static let inset: CGFloat = 40   // half a player cell: keeps goalkeepers inside the card
    static let midGap: CGFloat = 40  // keeps the two front lines apart

    static func point(x: Double, y: Double, home: Bool, in size: CGSize) -> CGPoint {
        let depth = CGFloat(y) * (size.height / 2 - inset - midGap)
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
        .aspectRatio(2.0 / 3.0, contentMode: .fit)
        .padding(.horizontal, 8)
    }
}

/// Thin white field lines at 15 %: drawn, never a photo of grass (design.md §7).
private struct PitchMarkings: View {
    var body: some View {
        Canvas { context, size in
            let w = size.width, h = size.height
            var lines = Path()
            lines.addRect(CGRect(x: 0.5, y: 0.5, width: w - 1, height: h - 1))
            lines.move(to: CGPoint(x: 0, y: h / 2))
            lines.addLine(to: CGPoint(x: w, y: h / 2))
            let r = w * 0.14
            lines.addEllipse(in: CGRect(x: w / 2 - r, y: h / 2 - r, width: 2 * r, height: 2 * r))
            for top in [true, false] {
                for box in [CGSize(width: w * 0.56, height: h * 0.14), CGSize(width: w * 0.26, height: h * 0.05)] {
                    lines.addRect(CGRect(x: (w - box.width) / 2, y: top ? 0.5 : h - box.height - 0.5,
                                         width: box.width, height: box.height))
                }
            }
            context.stroke(lines, with: .color(.white.opacity(0.15)), lineWidth: 1)
        }
        .accessibilityHidden(true)
    }
}

private struct PitchPlayer: View {
    let player: LineupPlayer

    var body: some View {
        NavigationLink(value: Route.player(player.player.id)) {
            VStack(spacing: 2) {
                Logo(url: player.player.photoUrl, size: 36, label: player.player.name, round: true)
                Text(player.player.name.split(separator: " ").last.map(String.init) ?? player.player.name)
                    .font(.caption2.weight(.semibold))
                    .foregroundStyle(Color.textPrimary)
                    .lineLimit(1)
                    .minimumScaleFactor(0.8)
                Text(player.rating.map { String(format: "%.1f", $0) } ?? " ")  // " " keeps every cell the same height
                    .font(.digits(13, relativeTo: .caption2, bold: false))
                    .foregroundStyle(Color.textSecondary)
            }
            .frame(width: 72)
            .contentShape(Rectangle())
            .accessibilityElement(children: .ignore)
            .accessibilityLabel(player.player.name + (player.rating.map { String(format: ", rating %.1f", $0) } ?? ""))
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
                if let minute = player.subIn {
                    Image(systemName: "arrow.up").font(.footnote.weight(.semibold)).foregroundStyle(Color.textSecondary)
                    Text("\(minute)'").font(.digits(17, relativeTo: .body, bold: false)).foregroundStyle(Color.textSecondary)
                }
                if let number = player.shirtNumber {
                    Text("\(number)")
                        .font(.digits(17, relativeTo: .body, bold: false))
                        .foregroundStyle(Color.textTertiary)
                        .frame(width: 28, alignment: .trailing)
                }
            }
            .padding(.horizontal, 16)
            .frame(minHeight: 48)
            .contentShape(Rectangle())
            .accessibilityElement(children: .ignore)
            .accessibilityLabel(player.subIn.map { "\(player.player.name), came on at \($0) minutes" } ?? player.player.name)
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
