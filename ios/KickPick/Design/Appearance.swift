import UIKit

/// Condensed SF titles (design.md §4) and a material navigation bar; the tab bar is our own (KickPickApp).
enum Appearance {
    static func apply() {
        let large = UIFontMetrics(forTextStyle: .largeTitle)
            .scaledFont(for: .systemFont(ofSize: 34, weight: .bold, width: .condensed))
        let inline = UIFontMetrics(forTextStyle: .headline)
            .scaledFont(for: .systemFont(ofSize: 17, weight: .semibold, width: .condensed))
        let top = UINavigationBarAppearance()
        top.configureWithTransparentBackground()
        top.largeTitleTextAttributes = [.font: large, .foregroundColor: UIColor.white]
        top.titleTextAttributes = [.font: inline, .foregroundColor: UIColor.white]
        let scrolled = top.copy()
        scrolled.backgroundEffect = UIBlurEffect(style: .systemUltraThinMaterialDark)
        UINavigationBar.appearance().scrollEdgeAppearance = top
        UINavigationBar.appearance().standardAppearance = scrolled
        UINavigationBar.appearance().compactAppearance = scrolled
    }
}
