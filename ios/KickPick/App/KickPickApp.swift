import SwiftUI

@main
struct KickPickApp: App {
    init() {
        URLCache.shared = URLCache(memoryCapacity: 50 << 20, diskCapacity: 200 << 20)
        Appearance.apply()
    }

    var body: some Scene {
        WindowGroup {
            RootView()
                .tint(.white)
                .preferredColorScheme(.dark)
        }
    }
}

/// Two tabs, each its own navigation stack, under our glass tab bar.
/// The bar shows only on the tabs' root screens and slides away once a screen is pushed.
private struct RootView: View {
    private enum RootTab { case matches, competitions }
    @State private var tab = RootTab.matches
    @State private var matchesPath: [Route] = []
    @State private var competitionsPath: [Route] = []
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    private var pushed: Bool { !(tab == .matches ? matchesPath : competitionsPath).isEmpty }

    var body: some View {
        TabView(selection: $tab) {
            NavigationStack(path: $matchesPath) { MatchesView().withRoutes() }
                .toolbar(.hidden, for: .tabBar)
                .tag(RootTab.matches)
            NavigationStack(path: $competitionsPath) { CompetitionsView().withRoutes() }
                .toolbar(.hidden, for: .tabBar)
                .tag(RootTab.competitions)
        }
        // our glass bar instead of the system one; pages scroll beneath it
        .safeAreaInset(edge: .bottom) {
            if !pushed {
                SegmentedPicker(options: [(.matches, "Matches"), (.competitions, "Competitions")], selection: $tab,
                                icons: ["sportscourt", "trophy"])
                    .frame(width: 240)  // no .isTabBar trait: it makes VoiceOver list every tab twice
                    .transition(reduceMotion ? .opacity : .move(edge: .bottom).combined(with: .opacity))
            }
        }
        .animation(.easeInOut(duration: 0.25), value: pushed)
    }
}
