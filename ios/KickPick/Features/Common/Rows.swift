import SwiftUI

/// Rows inside a glass card, separated by hairlines.
struct Rows<Item: Identifiable, Row: View>: View {
    let items: [Item]
    @ViewBuilder let row: (Item) -> Row

    var body: some View {
        ForEach(Array(items.enumerated()), id: \.element.id) { index, item in
            if index > 0 { Hairline() }
            row(item)
        }
    }
}
