import SwiftUI

// Tokens from design.md §3.
extension Color {
    static let textPrimary = Color.white
    static let textSecondary = Color.white.opacity(0.64)
    static let textTertiary = Color.white.opacity(0.52)
    static let onAccent = Color(red: 0x11 / 255, green: 0x11 / 255, blue: 0x13 / 255)
    static let hairline = Color.white.opacity(0.10)
    static let glassTint = Color.white.opacity(0.06)
    static let rowHighlight = Color.white.opacity(0.10)  // this team's row in a table
    static let skeleton = Color.white.opacity(0.08)  // loading bars and circles
    static let solidSurface = Color(red: 0x2C / 255, green: 0x2C / 255, blue: 0x30 / 255)
    static let cardYellow = Color(red: 1, green: 0xD6 / 255, blue: 0x0A / 255)
    static let cardRed = Color(red: 1, green: 0x45 / 255, blue: 0x3A / 255)
    static let win = Color(red: 0x30 / 255, green: 0xD1 / 255, blue: 0x58 / 255)  // form letters and ratings only
    static let loss = cardRed
    static let standout = Color(red: 0x0A / 255, green: 0x84 / 255, blue: 1)  // iOS dark-mode blue: ratings of 8+

    /// A match rating's colour: under 6 red, 6–6.9 yellow, 7–7.9 green (the form's), 8 and up blue.
    static func rating(_ value: Double) -> Color {
        switch value {
        case ..<6: loss
        case ..<7: cardYellow
        case ..<8: win
        default: standout
        }
    }
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
    static let app = Locale(identifier: "en_GB")  // "13 Oct", 24-hour time
}

extension Color {
    /// "#2AD572" → a colour; nil for anything else.
    init?(hex: String) {
        guard hex.count == 7, hex.hasPrefix("#"), let value = UInt32(hex.dropFirst(), radix: 16) else { return nil }
        self.init(red: Double(value >> 16 & 0xFF) / 255, green: Double(value >> 8 & 0xFF) / 255, blue: Double(value & 0xFF) / 255)
    }
}
