import SwiftUI

@main
struct KickPickApp: App {
    private enum RootTab { case matches, competitions }
    @State private var tab = RootTab.matches

    init() {
        URLCache.shared = URLCache(memoryCapacity: 50 << 20, diskCapacity: 200 << 20)
        Appearance.apply()
    }

    var body: some Scene {
        WindowGroup {
            TabView(selection: $tab) {
                NavigationStack { MatchesView().withRoutes() }
                    .toolbar(.hidden, for: .tabBar)
                    .tag(RootTab.matches)
                NavigationStack { CompetitionsView().withRoutes() }
                    .toolbar(.hidden, for: .tabBar)
                    .tag(RootTab.competitions)
            }
            // our glass bar instead of the system one; pages scroll beneath it
            .safeAreaInset(edge: .bottom) {
                SegmentedPicker(options: [(.matches, "Matches"), (.competitions, "Competitions")], selection: $tab,
                                icons: ["sportscourt", "trophy"])
                    .frame(width: 240)  // no .isTabBar trait: it makes VoiceOver list every tab twice
            }
            .tint(.white)
            .preferredColorScheme(.dark)
        }
    }
}
