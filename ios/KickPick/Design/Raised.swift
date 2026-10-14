import SwiftUI

/// Raised capsule from design.md §6.2: light from above, two-layer shadow below.
struct RaisedCapsule: View {
    var white = true
    var pressed = false

    var body: some View {
        let shape = Capsule()
        Group {
            if white {
                shape.fill(LinearGradient(colors: pressed ? [Color(white: 0.96), Color(white: 0.86)]
                                                          : [.white, Color(white: 0.894)],
                                          startPoint: .top, endPoint: .bottom))
            } else {
                GlassBackground(shape: shape)
            }
        }
        .overlay(shape.strokeBorder(LinearGradient(colors: [.white.opacity(white ? 1 : 0.5), .clear],
                                                   startPoint: .top, endPoint: .center), lineWidth: 1))
        .overlay(shape.strokeBorder(LinearGradient(colors: [.clear, .black.opacity(0.12)],
                                                   startPoint: .center, endPoint: .bottom), lineWidth: 1))
        .shadow(color: .black.opacity(0.30), radius: 1, y: 1)
        .shadow(color: .black.opacity(0.35), radius: pressed ? 4 : 16, y: pressed ? 2 : 8)
    }
}

struct RaisedButtonStyle: ButtonStyle {
    var white = true
    var icon = false
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.body.weight(.semibold))
            .foregroundStyle(white ? Color.onAccent : Color.textPrimary)
            .padding(.horizontal, icon ? 0 : 24)
            .frame(minWidth: icon ? 50 : nil, minHeight: 50)
            .background(RaisedCapsule(white: white, pressed: configuration.isPressed))
            .scaleEffect(configuration.isPressed && !reduceMotion ? 0.97 : 1)
            .animation(.spring(response: 0.25, dampingFraction: 0.7), value: configuration.isPressed)
            .sensoryFeedback(.impact(weight: .light), trigger: configuration.isPressed) { _, pressed in pressed }
    }
}

extension ButtonStyle where Self == RaisedButtonStyle {
    static var primary: RaisedButtonStyle { RaisedButtonStyle(white: true) }
    static var glass: RaisedButtonStyle { RaisedButtonStyle(white: false) }
    static var glassIcon: RaisedButtonStyle { RaisedButtonStyle(white: false, icon: true) }
}
