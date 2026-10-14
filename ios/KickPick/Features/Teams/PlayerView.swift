import SwiftUI

struct PlayerView: View {
    let id: Int
    @State private var tab = Tab.matches

    enum Tab: Hashable { case matches, stats, career }

    var body: some View {
        ScrollView {
            Loader { try await APIClient.shared.player(id) } content: { player in
                VStack(spacing: 24) {
                    PlayerHeader(player: player)
                    if !player.facts.isEmpty { FactsCard(facts: player.facts) }
                    SegmentedPicker(options: [(.matches, "Matches"), (.stats, "Stats"), (.career, "Career")],
                                    selection: $tab)
                    switch tab {
                    case .matches: MatchesTab(matches: player.matches)
                    case .stats: StatsTab(seasons: player.seasons)
                    case .career: CareerTab(career: player.career)
                    }
                }
            }
            .padding(16)
        }
        .screen()
        .navigationBarTitleDisplayMode(.inline)
    }
}

/// Photo, name (the bar shows it once this scrolls away), club and shirt number.
private struct PlayerHeader: View {
    let player: PlayerPage

    var body: some View {
        VStack(spacing: 12) {
            Logo(url: player.photoUrl, size: 96, label: player.name, round: true)
            VStack(spacing: 0) {
                Text(player.name)
                    .font(.title2.weight(.bold).width(.condensed))
                    .foregroundStyle(Color.textPrimary)
                    .multilineTextAlignment(.center)
                    .accessibilityAddTraits(.isHeader)
                    .revealsInBar {
                        Text(player.name).font(.headline.width(.condensed)).foregroundStyle(Color.textPrimary)
                    }
                if let club = player.teams.first {
                    NavigationLink(value: Route.team(club.team.id)) {
                        Text(club.shirtNumber.map { "\(club.team.name) · No. \($0)" } ?? club.team.name)
                            .font(.subheadline.weight(.semibold))
                            .foregroundStyle(Color.textSecondary)
                            .frame(minHeight: 44)
                            .contentShape(Rectangle())
                    }
                    .buttonStyle(.plain)
                }
            }
        }
        .frame(maxWidth: .infinity)
    }
}

private typealias Fact = (label: String, value: String, flag: URL?)

private extension PlayerPage {
    var facts: [Fact] {
        let positions = ["Coach": "Coach", "GK": "Goalkeeper", "DF": "Defender", "MF": "Midfielder", "FW": "Forward"]
        var out: [Fact] = []
        if let position { out.append((label: "Position", value: positions[position] ?? position, flag: nil)) }
        if let birthDate, let line = Self.ageLine(birthDate: birthDate) { out.append((label: "Age", value: line, flag: nil)) }
        if let country = countryName ?? countryCode { out.append((label: "Country", value: country, flag: flagUrl)) }
        return out
    }
}

private struct FactsCard: View {
    let facts: [Fact]

    var body: some View {
        VStack(spacing: 0) {
            ForEach(Array(facts.enumerated()), id: \.offset) { index, fact in
                if index > 0 { Hairline() }
                HStack(spacing: 8) {
                    Text(fact.label).foregroundStyle(Color.textSecondary)
                    Spacer()
                    if let flag = fact.flag { Logo(url: flag, size: 20, label: fact.value).accessibilityHidden(true) }
                    Text(fact.value).foregroundStyle(Color.textPrimary)
                }
                .font(.body)
                .padding(.horizontal, 16)
                .frame(minHeight: 44)
                .accessibilityElement(children: .combine)
            }
        }
        .glassCard()
    }
}

private struct MatchesTab: View {
    let matches: [PlayerMatch]

    var body: some View {
        if matches.isEmpty {
            EmptyState(text: "No matches")
        } else {
            CardSection(title: nil) {
                Rows(items: matches) { item in
                    NavigationLink(value: Route.match(item.match.id)) {
                        HStack(spacing: 0) {
                            MatchRow(match: item.match, showDate: true)
                            VStack(alignment: .trailing, spacing: 2) {
                                Text(item.rating.map { String(format: "%.1f", $0) } ?? "–")
                                    .font(.digits(20, relativeTo: .title3))
                                    .foregroundStyle(Color.textPrimary)
                                Text("\(item.minutes)'").font(.footnote.weight(.medium)).foregroundStyle(Color.textSecondary)
                            }
                            .frame(width: 40, alignment: .trailing)
                            .padding(.trailing, 16)
                        }
                        .accessibilityElement(children: .combine)
                    }
                    .buttonStyle(.plain)
                }
            }
        }
    }
}

private let statWidths: [CGFloat] = [36, 28, 28, 40]

/// Column titles above the first row, like the standings table.
private struct ColumnsHeader: View {
    let first: String
    let columns: [String]

    var body: some View {
        HStack(spacing: 8) {
            Text(first)
            Spacer()
            ForEach(Array(columns.enumerated()), id: \.offset) { index, title in
                Text(title).frame(width: statWidths[index], alignment: .trailing)
            }
        }
        .font(.footnote.weight(.medium))
        .foregroundStyle(Color.textTertiary)
        .padding(.horizontal, 16)
        .padding(.top, 12)
        .padding(.bottom, 4)
        .accessibilityHidden(true)
    }
}

/// A competition or club with digit columns on the right.
private struct StatLine: View {
    let logo: URL?
    let title: String
    let subtitle: String?
    let values: [String]

    var body: some View {
        HStack(spacing: 8) {
            Logo(url: logo, size: 24, label: title)
            VStack(alignment: .leading, spacing: 2) {
                Text(title).font(.body).foregroundStyle(Color.textPrimary).lineLimit(1)
                if let subtitle { Text(subtitle).font(.footnote).foregroundStyle(Color.textSecondary).lineLimit(1) }
            }
            Spacer(minLength: 4)
            ForEach(Array(values.enumerated()), id: \.offset) { index, value in
                Text(value)
                    .font(.digits(17, relativeTo: .body, bold: false))
                    .foregroundStyle(Color.textPrimary)
                    .frame(width: statWidths[index], alignment: .trailing)
            }
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 10)
        .accessibilityElement(children: .combine)
    }
}

private func number(_ value: Int?) -> String { value.map(String.init) ?? "–" }

private struct StatsTab: View {
    let seasons: [SeasonStats]

    var body: some View {
        if seasons.isEmpty {
            EmptyState(text: "No stats yet")
        } else {
            VStack(spacing: 24) {
                ForEach(seasons.grouped(by: \.season)) { group in
                    CardSection(title: group.key) {
                        ColumnsHeader(first: "Competition", columns: ["Apps", "G", "A", "Rating"])
                        Rows(items: group.items) { stats in
                            StatLine(logo: stats.competition.logoUrl, title: stats.competition.name ?? "—",
                                     subtitle: stats.team.name,
                                     values: [number(stats.appearances), number(stats.goals), number(stats.assists),
                                              stats.rating.map { String(format: "%.1f", $0) } ?? "–"])
                        }
                    }
                }
            }
        }
    }
}

private struct CareerTab: View {
    let career: [CareerEntry]
    private static let titles = ["senior": "Clubs", "national": "National team", "youth": "Youth", "coach": "Coaching"]

    var body: some View {
        if career.isEmpty {
            EmptyState(text: "No career data")
        } else {
            VStack(spacing: 24) {
                ForEach(career.grouped(by: \.kind)) { group in
                    CardSection(title: Self.titles[group.key] ?? group.key.capitalized) {
                        ColumnsHeader(first: "Team", columns: ["Apps", "G"])
                        Rows(items: group.items) { entry in
                            StatLine(logo: entry.team.logoUrl, title: entry.team.name ?? "—", subtitle: entry.years,
                                     values: [number(entry.appearances), number(entry.goals)])
                        }
                    }
                }
            }
        }
    }
}

extension CareerEntry {
    /// "2022 – now", "2016 – 2022"
    var years: String {
        let start = startDate.map { String($0.prefix(4)) } ?? "?"
        return "\(start) – " + (endDate.map { String($0.prefix(4)) } ?? "now")
    }
}

extension PlayerPage {
    /// "26 · 21 Jul 2000" — computed and formatted in GMT, so the day never shifts with the device's time zone.
    static func ageLine(birthDate: String, now: Date = .now) -> String? {
        guard let born = try? Date(birthDate + "T00:00:00Z", strategy: .iso8601) else { return nil }
        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = .gmt
        guard let age = calendar.dateComponents([.year], from: born, to: now).year else { return nil }
        var style = Date.FormatStyle.dateTime.day().month(.abbreviated).year().locale(.app)
        style.timeZone = .gmt
        return "\(age) · \(born.formatted(style))"
    }
}
