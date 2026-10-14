import SwiftUI
import UIKit

/// Round raised glass back button, the same as the other icon buttons (design.md §6.2).
struct BackButton: View {
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        Button { dismiss() } label: { Image(systemName: "chevron.left") }
            .buttonStyle(.glassIcon)
            .accessibilityLabel("Назад")
    }
}

/// A toolbar item that draws its own glass: iOS 26 would otherwise wrap it in a second, system one.
struct GlassToolbarItem<Content: View>: ToolbarContent {
    let placement: ToolbarItemPlacement
    @ViewBuilder let content: Content

    var body: some ToolbarContent {
        if #available(iOS 26, *) {
            ToolbarItem(placement: placement) { content }.sharedBackgroundVisibility(.hidden)
        } else {
            ToolbarItem(placement: placement) { content }
        }
    }
}

extension View {
    /// Swaps the system back button for `BackButton`.
    func glassBackButton() -> some View {
        navigationBarBackButtonHidden().toolbar { GlassToolbarItem(placement: .topBarLeading) { BackButton() } }
    }
}

/// Hiding the system back button also turns off swipe-back; this turns it on again.
extension UINavigationController: @retroactive UIGestureRecognizerDelegate {
    override open func viewDidLoad() {
        super.viewDidLoad()
        interactivePopGestureRecognizer?.delegate = self
    }

    public func gestureRecognizerShouldBegin(_ gestureRecognizer: UIGestureRecognizer) -> Bool {
        viewControllers.count > 1
    }
}
