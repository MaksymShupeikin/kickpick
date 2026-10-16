import SwiftUI

/// The saved pre-match forecast remains clearly labelled when the match goes live.
struct PredictionCard: View {
    let match: Match
    let prediction: MatchPrediction
    @Environment(\.dynamicTypeSize) private var typeSize

    private var probabilities: MatchPrediction.Probabilities { prediction.probabilities }

    var body: some View {
        CardSection(title: "Pre-match forecast") {  // the title says it's from before kick-off, live or not
            VStack(alignment: .leading, spacing: 16) {
                if typeSize >= .xxxLarge {
                    VStack(spacing: 12) {
                        outcomeRow("Home", spoken: "Home win, \(match.home.name)", probability: probabilities.home)
                        outcomeRow("Draw", spoken: "Draw", probability: probabilities.draw)
                        outcomeRow("Away", spoken: "Away win, \(match.away.name)", probability: probabilities.away)
                    }
                } else {
                    HStack(alignment: .top, spacing: 8) {
                        outcomeColumn("Home", spoken: "Home win, \(match.home.name)", probability: probabilities.home)
                        outcomeColumn("Draw", spoken: "Draw", probability: probabilities.draw)
                        outcomeColumn("Away", spoken: "Away win, \(match.away.name)", probability: probabilities.away)
                    }
                }
                probabilityBar
            }
            .padding(16)
        }
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier("matchPredictionCard")
    }

    private func outcomeColumn(_ title: String, spoken: String, probability: Double) -> some View {
        VStack(spacing: 4) {
            percentage(probability)
            Text(title)
                .font(.footnote.weight(probability == probabilities.highest ? .semibold : .regular))
                .foregroundStyle(probability == probabilities.highest ? Color.textPrimary : .textSecondary)
                .multilineTextAlignment(.center)
                .fixedSize(horizontal: false, vertical: true)
        }
        .frame(maxWidth: .infinity)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(spoken)
        .accessibilityValue(probability.formatted(.percent.precision(.fractionLength(1)).locale(.app)))
    }

    private func outcomeRow(_ title: String, spoken: String, probability: Double) -> some View {
        HStack(spacing: 12) {
            Text(title)
                .font(.body)
                .foregroundStyle(Color.textPrimary)
                .fixedSize(horizontal: false, vertical: true)
            Spacer(minLength: 0)
            percentage(probability).fixedSize()
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(spoken)
        .accessibilityValue(probability.formatted(.percent.precision(.fractionLength(1)).locale(.app)))
    }

    private func percentage(_ value: Double) -> some View {
        HStack(alignment: .firstTextBaseline, spacing: 1) {
            Text((value * 100).formatted(.number.precision(.fractionLength(1)).locale(.app)))
                .font(.digits(32, relativeTo: .title, bold: value == probabilities.highest))
            Text("%")
                .font(.footnote.weight(.medium))
        }
        .monospacedDigit()
        .foregroundStyle(value == probabilities.highest ? Color.textPrimary : .textSecondary)
    }

    /// Same four-point proportions as the match stats; home, draw, away left to right.
    private var probabilityBar: some View {
        GeometryReader { geometry in
            let width = max(0, geometry.size.width - 4)
            HStack(spacing: 2) {
                segment(probabilities.home, width: width, color: .textPrimary)
                segment(probabilities.draw, width: width, color: .textSecondary)
                segment(probabilities.away, width: width, color: .white.opacity(0.3))
            }
        }
        .frame(height: 4)
        .accessibilityHidden(true)
    }

    private func segment(_ probability: Double, width: CGFloat, color: Color) -> some View {
        Capsule().fill(color).frame(width: width * CGFloat(probability))
    }
}
