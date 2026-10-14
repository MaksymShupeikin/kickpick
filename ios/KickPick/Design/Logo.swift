import SwiftUI

/// Real crest, league logo or player photo by URL from the API.
/// While loading or on failure: an empty glass circle — never a made-up image (design.md §7).
struct Logo: View {
    let url: URL?
    let size: CGFloat
    let label: String
    var round = false

    var body: some View {
        AsyncImage(url: url) { phase in
            if let image = phase.image {
                image.resizable().scaledToFit()
                    .clipShape(round ? AnyShape(Circle()) : AnyShape(Rectangle()))
            } else {
                Circle().fill(Color.glassTint)
            }
        }
        .frame(width: size, height: size)
        .accessibilityLabel(label)
    }
}
