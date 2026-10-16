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

extension View {
    /// For tabs pinned as a section header: once they stick under the navigation bar, the bar's frosted material
    /// extends behind them, so content scrolls under one bar instead of showing around the pill.
    func joinsBarWhenPinned() -> some View {
        modifier(JoinsBarWhenPinned())
    }
}

private struct JoinsBarWhenPinned: ViewModifier {
    @State private var pinned = false
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    func body(content: Content) -> some View {
        content
            .background {
                Rectangle()
                    .fill(.ultraThinMaterial)  // the scrolled bar's material (Appearance)
                    .padding(.horizontal, -16)  // out to the screen edges, past the page padding
                    .padding(.bottom, -8)
                    .opacity(pinned ? 1 : 0)
            }
            // a pinned header sits at the bar's bottom edge, the .scrollView origin
            .onGeometryChange(for: Bool.self) { $0.frame(in: .scrollView).minY < 1 } action: { stuck in
                withAnimation(reduceMotion ? nil : .easeInOut(duration: 0.2)) { pinned = stuck }
            }
    }
}

extension View {
    /// Put on the stack whose pinned section header holds the tabs. When `value` (the tab) changes while the page is
    /// scrolled past the tabs, the page returns to where they start, so the new tab shows from its top. Otherwise a
    /// shorter tab leaves the lazy stack scrolled beyond its end, and it draws nothing at all, tabs included.
    func scrollsToTabs<Value: Equatable>(on value: Value) -> some View {
        modifier(ScrollsToTabs(value: value))
    }
}

private struct ScrollsToTabs<Value: Equatable>: ViewModifier {
    let value: Value
    @State private var scrolledPast = false

    func body(content: Content) -> some View {
        ScrollViewReader { proxy in
            content
                .id(ScrollsToTabsID())
                .onGeometryChange(for: Bool.self) { $0.frame(in: .scrollView).minY < 0 } action: { scrolledPast = $0 }
                .onChange(of: value) { if scrolledPast { proxy.scrollTo(ScrollsToTabsID(), anchor: .top) } }
        }
    }
}

private struct ScrollsToTabsID: Hashable {}
