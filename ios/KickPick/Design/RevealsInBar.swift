import SwiftUI

extension View {
    /// Once this view has scrolled fully under the navigation bar, `mini` fades in at the bar's centre, and fades
    /// out when the view comes back (design.md §6.3). Put it on a pushed screen's main block.
    func revealsInBar<Mini: View>(@ViewBuilder _ mini: () -> Mini) -> some View {
        modifier(RevealsInBar(mini: mini()))
    }
}

private struct RevealsInBar<Mini: View>: ViewModifier {
    let mini: Mini
    @State private var hidden = false
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    func body(content: Content) -> some View {
        content
            // the .scrollView space starts at the bar's bottom edge (measured: 126 pt at rest, −23 once under the bar)
            .onGeometryChange(for: Bool.self) { $0.frame(in: .scrollView).maxY < 0 } action: { gone in
                withAnimation(reduceMotion ? nil : .easeInOut(duration: 0.2)) { hidden = gone }
            }
            .toolbar {
                GlassToolbarItem(placement: .principal) {
                    mini.opacity(hidden ? 1 : 0).accessibilityHidden(!hidden)
                }
            }
    }
}
