import SwiftUI

// Tokens from design.md §3.
extension Color {
    static let textPrimary = Color.white
    static let textSecondary = Color.white.opacity(0.64)
    static let textTertiary = Color.white.opacity(0.52)
    static let onAccent = Color(red: 0x11 / 255, green: 0x11 / 255, blue: 0x13 / 255)
    static let hairline = Color.white.opacity(0.10)
    static let glassTint = Color.white.opacity(0.06)
    static let solidSurface = Color(red: 0x2C / 255, green: 0x2C / 255, blue: 0x30 / 255)
    static let cardYellow = Color(red: 1, green: 0xD6 / 255, blue: 0x0A / 255)
    static let cardRed = Color(red: 1, green: 0x45 / 255, blue: 0x3A / 255)
}

extension LinearGradient {
    static let glassStroke = LinearGradient(colors: [.white.opacity(0.22), .white.opacity(0.05)],
                                            startPoint: .top, endPoint: .bottom)
}

extension Font {
    /// Barlow Condensed — digits only: the font has no Cyrillic.
    static func digits(_ size: CGFloat, relativeTo style: Font.TextStyle, bold: Bool = true) -> Font {
        .custom(bold ? "BarlowCondensed-Bold" : "BarlowCondensed-SemiBold", size: size, relativeTo: style)
    }

    static let sectionTitle = Font.system(.title3, weight: .semibold).width(.condensed)
}

extension Locale {
    static let app = Locale(identifier: "ru_RU")
}
