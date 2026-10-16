import SwiftUI

/// App splash screen displaying the KickPick horizontal logo over our custom gradient background (`design.md §3.1`).
/// Aligns with the system launch screen (`UILaunchScreen`) for a seamless handover without visual jumping.
struct SplashScreenView: View {
    var onDismiss: (() -> Void)? = nil

    var body: some View {
        ZStack {
            AppBackground()

            Image("LaunchLogo")
                .accessibilityLabel("KickPick")
        }
        .contentShape(Rectangle())
        .onTapGesture {
            onDismiss?()
        }
    }
}

#Preview {
    SplashScreenView()
}
