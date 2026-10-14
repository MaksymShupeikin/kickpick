import SwiftUI

/// Gray gradient with two soft white light spots for the glass to blur (design.md §3.1).
struct AppBackground: View {
    var body: some View {
        GeometryReader { geo in
            let radius = geo.size.width * 0.6
            ZStack {
                LinearGradient(colors: [Color(red: 0x2B / 255, green: 0x2B / 255, blue: 0x2F / 255),
                                        Color(red: 0x1A / 255, green: 0x1A / 255, blue: 0x1D / 255)],
                               startPoint: .top, endPoint: .bottom)
                RadialGradient(colors: [.white.opacity(0.07), .clear], center: UnitPoint(x: 0.1, y: 0.08),
                               startRadius: 0, endRadius: radius)
                RadialGradient(colors: [.white.opacity(0.07), .clear], center: UnitPoint(x: 0.95, y: 0.5),
                               startRadius: 0, endRadius: radius)
            }
        }
        .ignoresSafeArea()
    }
}

extension View {
    func screen() -> some View {
        background { AppBackground() }
    }
}
