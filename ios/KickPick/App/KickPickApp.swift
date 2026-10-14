import SwiftUI

@main
struct KickPickApp: App {
    init() {
        URLCache.shared = URLCache(memoryCapacity: 50 << 20, diskCapacity: 200 << 20)
        Appearance.apply()
    }

    var body: some Scene {
        WindowGroup {
            TabView {
                NavigationStack { MatchesView().withRoutes() }
                    .tabItem { Label("Матчи", systemImage: "sportscourt") }
                NavigationStack { CompetitionsView().withRoutes() }
                    .tabItem { Label("Турниры", systemImage: "trophy") }
            }
            .tint(.white)
            .preferredColorScheme(.dark)
        }
    }
}
