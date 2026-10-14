import SwiftUI

/// Rounds as columns; pairs spread evenly so each sits opposite its two feeders. No connector lines in the skeleton.
struct BracketView: View {
    let bracket: Bracket
    private let cardHeight: CGFloat = 76

    var body: some View {
        let tallest = CGFloat(bracket.rounds.map(\.matchups.count).max() ?? 1) * (cardHeight + 12)
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(alignment: .top, spacing: 16) {
                ForEach(bracket.rounds, id: \.stage) { round in
                    column(roundTitle(round.stage)) {
                        VStack(spacing: 0) {
                            ForEach(round.matchups.indices, id: \.self) { index in
                                Spacer(minLength: 6)
                                MatchupCard(matchup: round.matchups[index]).frame(height: cardHeight)
                                Spacer(minLength: 6)
                            }
                        }
                        .frame(height: tallest)
                    }
                }
                if let third = bracket.thirdPlace {
                    column(roundTitle("bronze")) { MatchupCard(matchup: third).frame(height: cardHeight) }
                }
            }
            .padding(.vertical, 4)
        }
    }

    private func column<Content: View>(_ title: String, @ViewBuilder content: () -> Content) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(title).font(.sectionTitle).foregroundStyle(Color.textSecondary).accessibilityAddTraits(.isHeader)
            content()
        }
        .frame(width: 220)
    }
}

private struct MatchupCard: View {
    let matchup: Matchup

    var body: some View {
        let card = VStack(spacing: 8) {
            line(matchup.home, score: matchup.homeScore)
            line(matchup.away, score: matchup.awayScore)
        }
        .padding(.horizontal, 12)
        .frame(maxHeight: .infinity)
        .glassCard(radius: 12)
        if let id = matchup.matchIds.last {
            NavigationLink(value: Route.match(id)) { card }.buttonStyle(.plain)
        } else {
            card
        }
    }

    private func line(_ team: TeamRef?, score: Int?) -> some View {
        let lost = team != nil && matchup.winnerId != nil && team?.id != matchup.winnerId
        let color = lost ? Color.textSecondary : Color.textPrimary
        return HStack(spacing: 8) {
            if let team {
                Logo(url: team.logoUrl, size: 20, label: team.name)
                Text(team.name).font(.subheadline.weight(lost ? .regular : .semibold)).foregroundStyle(color).lineLimit(1)
            } else {
                Text("—").font(.subheadline).foregroundStyle(Color.textTertiary).accessibilityLabel("To be decided")
            }
            Spacer(minLength: 4)
            if let score {
                Text("\(score)").font(.digits(17, relativeTo: .body)).monospacedDigit().foregroundStyle(color)
            }
        }
    }
}
