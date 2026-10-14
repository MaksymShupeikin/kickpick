import SwiftUI

struct Hairline: View {
    var body: some View {
        Rectangle().fill(Color.hairline).frame(height: 1).padding(.leading, 16)
    }
}

struct EmptyState: View {
    let text: String

    var body: some View {
        Text(text)
            .font(.subheadline)
            .foregroundStyle(Color.textTertiary)
            .frame(maxWidth: .infinity, minHeight: 120)
            .glassCard()
    }
}

struct ErrorState: View {
    let retry: () -> Void

    var body: some View {
        VStack(spacing: 16) {
            Text("Не удалось загрузить").font(.subheadline).foregroundStyle(Color.textSecondary)
            Button("Повторить", action: retry).buttonStyle(.glass)
        }
        .frame(maxWidth: .infinity)
        .padding(24)
        .glassCard()
    }
}

/// Title outside, one glass card with rows inside (design.md §8).
struct CardSection<Content: View>: View {
    let title: String?
    var logo: URL? = nil
    @ViewBuilder let content: Content

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            if let title {
                HStack(spacing: 8) {
                    if let logo { Logo(url: logo, size: 20, label: title) }
                    Text(title).font(.subheadline.weight(.semibold)).foregroundStyle(Color.textSecondary)
                }
                .padding(.horizontal, 4)
                .accessibilityAddTraits(.isHeader)
            }
            VStack(spacing: 0) { content }.glassCard()
        }
    }
}
