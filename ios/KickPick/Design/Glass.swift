import SwiftUI

/// Frosted glass from design.md §6.1; solid when Reduce Transparency is on.
struct GlassBackground<S: InsettableShape>: View {
    let shape: S
    @Environment(\.accessibilityReduceTransparency) private var reduceTransparency

    var body: some View {
        Group {
            if reduceTransparency {
                shape.fill(Color.solidSurface)
            } else {
                shape.fill(.ultraThinMaterial).overlay(shape.fill(Color.glassTint))
            }
        }
        .overlay(shape.strokeBorder(LinearGradient.glassStroke, lineWidth: 1))
        .shadow(color: .black.opacity(0.25), radius: 24, y: 8)
    }
}

extension View {
    func glassCard(radius: CGFloat = 20) -> some View {
        background(GlassBackground(shape: RoundedRectangle(cornerRadius: radius, style: .continuous)))
    }
}
