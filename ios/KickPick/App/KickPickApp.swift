import SwiftUI

@main
struct KickPickApp: App {
    @State private var showingSplash = true
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    init() {
        URLCache.shared = URLCache(memoryCapacity: 50 << 20, diskCapacity: 200 << 20)
        Appearance.apply()
    }

    var body: some Scene {
        WindowGroup {
            ZStack {
                RootView()

                if showingSplash {
                    SplashScreenView(onDismiss: dismissSplash)
                        .transition(.opacity)
                        .zIndex(1)
                }
            }
            .tint(.white)
            .preferredColorScheme(.dark)
            .task {
                guard showingSplash else { return }
                try? await Task.sleep(nanoseconds: reduceMotion ? 350_000_000 : 850_000_000)
                dismissSplash()
            }
        }
    }

    private func dismissSplash() {
        withAnimation(.easeInOut(duration: reduceMotion ? 0.15 : 0.35)) {
            showingSplash = false
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
    @State private var barHeight: CGFloat = 0
    @State private var searching = false
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    private var pushed: Bool { !(tab == .matches ? matchesPath : competitionsPath).isEmpty }
    /// Off on pushed screens, and while the search is open: it would sit above the search's dimming, and above the
    /// keyboard over the suggestions.
    private var barHidden: Bool { pushed || searching }

    var body: some View {
        TabView(selection: $tab) {
            NavigationStack(path: $matchesPath) { MatchesView().withRoutes() }
                .environment(\.popToRoot) { matchesPath.removeAll() }
                .toolbar(.hidden, for: .tabBar)
                .tag(RootTab.matches)
            NavigationStack(path: $competitionsPath) { CompetitionsView().withRoutes() }
                .environment(\.popToRoot) { competitionsPath.removeAll() }
                .toolbar(.hidden, for: .tabBar)
                .tag(RootTab.competitions)
        }
        .environment(\.tabBarHeight, barHeight)
        .environment(\.searchOpened) { searching = $0 }
        // our glass bar instead of the system one; pages scroll beneath it
        .safeAreaInset(edge: .bottom) {
            if !barHidden {
                SegmentedPicker(options: [(.matches, "Matches"), (.competitions, "Competitions")], selection: $tab,
                                icons: ["sportscourt", "trophy"])
                    .frame(width: 240)  // no .isTabBar trait: it makes VoiceOver list every tab twice
                    .onGeometryChange(for: CGFloat.self) { $0.size.height } action: { barHeight = $0 }
                    .transition(reduceMotion ? .opacity : .move(edge: .bottom).combined(with: .opacity))
            }
        }
        .animation(.easeInOut(duration: 0.25), value: barHidden)
    }
}

extension EnvironmentValues {
    /// The floating tab bar's height: its safe-area inset doesn't reach into the tabs, so root lists pad for it.
    @Entry var tabBarHeight: CGFloat = 0
    /// Root screens report their search opening and closing, so the tab bar can step aside (a preference wouldn't
    /// cross the TabView back up).
    @Entry var searchOpened: (Bool) -> Void = { _ in }
    /// Back to the tab's first screen: what holding the back button does.
    @Entry var popToRoot: () -> Void = {}
}
