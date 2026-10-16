import SwiftUI

struct Hairline: View {
    var body: some View {
        Rectangle().fill(Color.hairline).frame(height: 1).padding(.leading, 16)
    }
}

/// An empty pitch with the ball on the centre spot above the message (design.md §8).
struct EmptyState: View {
    let text: String

    var body: some View {
        VStack(spacing: 16) {
            ZStack {
                PitchMarkings(opacity: 0.35)
                    .frame(width: 104, height: 168)
                    .rotationEffect(.degrees(90))  // lying across the card
                    .frame(width: 168, height: 104)
                    // the lines fade out towards the edges, so it reads as a picture rather than a diagram
                    .mask(RadialGradient(colors: [.black, .clear], center: .center, startRadius: 28, endRadius: 90))
                Image(systemName: "soccerball")
                    .font(.system(size: 16))
                    .foregroundStyle(Color.textSecondary)
            }
            .accessibilityHidden(true)
            Text(text)
                .font(.subheadline)
                .foregroundStyle(Color.textSecondary)
                .multilineTextAlignment(.center)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 28)
        .padding(.horizontal, 16)
        .glassCard()
    }
}

/// Thin white field lines (15 % by default), the long side vertical: drawn, never a photo of grass (design.md §7).
struct PitchMarkings: View {
    var opacity = 0.15

    var body: some View {
        Canvas { context, size in
            let w = size.width, h = size.height
            var lines = Path()
            lines.addRect(CGRect(x: 0.5, y: 0.5, width: w - 1, height: h - 1))
            lines.move(to: CGPoint(x: 0, y: h / 2))
            lines.addLine(to: CGPoint(x: w, y: h / 2))
            let r = w * 0.14
            lines.addEllipse(in: CGRect(x: w / 2 - r, y: h / 2 - r, width: 2 * r, height: 2 * r))
            for top in [true, false] {
                for box in [CGSize(width: w * 0.56, height: h * 0.14), CGSize(width: w * 0.26, height: h * 0.05)] {
                    lines.addRect(CGRect(x: (w - box.width) / 2, y: top ? 0.5 : h - box.height - 0.5,
                                         width: box.width, height: box.height))
                }
            }
            context.stroke(lines, with: .color(.white.opacity(opacity)), lineWidth: 1)
        }
        .accessibilityHidden(true)
    }
}


/// A shot off the post above the message: the load missed, have another go (design.md §8).
struct ErrorState: View {
    let retry: () -> Void

    var body: some View {
        VStack(spacing: 16) {
            OffThePost()
                .frame(width: 168, height: 104)
                .accessibilityHidden(true)
            VStack(spacing: 4) {
                Text("Couldn’t load").font(.subheadline.weight(.semibold)).foregroundStyle(Color.textPrimary)
                Text("Check your connection and try again.")
                    .font(.footnote)
                    .foregroundStyle(Color.textSecondary)
                    .multilineTextAlignment(.center)
            }
            Button("Try again", action: retry).buttonStyle(.glass)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 28)
        .padding(.horizontal, 16)
        .glassCard()
    }
}

/// A goal with its net, the dashed flight of a shot striking the right post, sparks where it hit, and the ball
/// flying off: drawn in white like the pitch markings, fading out towards the edges.
private struct OffThePost: View {
    var body: some View {
        GeometryReader { geo in
            let w = geo.size.width, h = geo.size.height
            let goal = CGRect(x: w * 0.24, y: h * 0.2, width: w * 0.52, height: h * 0.62)
            let hit = CGPoint(x: goal.maxX, y: goal.minY + goal.height * 0.3)
            let ball = CGPoint(x: w * 0.9, y: h * 0.16)
            ZStack {
                Canvas { context, _ in
                    var net = Path()  // the net behind the frame
                    for x in stride(from: goal.minX + 10, to: goal.maxX, by: 10) {
                        net.move(to: CGPoint(x: x, y: goal.minY)); net.addLine(to: CGPoint(x: x, y: goal.maxY))
                    }
                    for y in stride(from: goal.minY + 9, to: goal.maxY, by: 9) {
                        net.move(to: CGPoint(x: goal.minX, y: y)); net.addLine(to: CGPoint(x: goal.maxX, y: y))
                    }
                    context.stroke(net, with: .color(.white.opacity(0.12)), lineWidth: 0.75)

                    var ground = Path()
                    ground.move(to: CGPoint(x: 0, y: goal.maxY)); ground.addLine(to: CGPoint(x: w, y: goal.maxY))
                    context.stroke(ground, with: .color(.white.opacity(0.2)), lineWidth: 1)

                    var frame = Path()  // posts and crossbar
                    frame.move(to: CGPoint(x: goal.minX, y: goal.maxY))
                    frame.addLine(to: CGPoint(x: goal.minX, y: goal.minY))
                    frame.addLine(to: CGPoint(x: goal.maxX, y: goal.minY))
                    frame.addLine(to: CGPoint(x: goal.maxX, y: goal.maxY))
                    context.stroke(frame, with: .color(.white.opacity(0.6)),
                                   style: StrokeStyle(lineWidth: 2.5, lineCap: .round, lineJoin: .round))

                    var flight = Path()  // in from the bottom left, off the post, away to the top right
                    flight.move(to: CGPoint(x: w * 0.06, y: h * 0.98))
                    flight.addQuadCurve(to: hit, control: CGPoint(x: w * 0.42, y: h * 0.02))
                    flight.addQuadCurve(to: CGPoint(x: ball.x - 9, y: ball.y + 5), control: CGPoint(x: w * 0.84, y: h * 0.06))
                    context.stroke(flight, with: .color(.white.opacity(0.35)),
                                   style: StrokeStyle(lineWidth: 1, lineCap: .round, dash: [3, 4]))

                    var sparks = Path()  // where it struck the post
                    for angle in [-60.0, -10.0, 40.0] {
                        let a = angle * .pi / 180
                        sparks.move(to: CGPoint(x: hit.x + 5 * cos(a), y: hit.y + 5 * sin(a)))
                        sparks.addLine(to: CGPoint(x: hit.x + 10 * cos(a), y: hit.y + 10 * sin(a)))
                    }
                    context.stroke(sparks, with: .color(.white.opacity(0.7)), style: StrokeStyle(lineWidth: 1.5, lineCap: .round))
                }
                Image(systemName: "soccerball")
                    .font(.system(size: 16))
                    .foregroundStyle(Color.textSecondary)
                    .position(ball)
            }
        }
        // like the empty pitch: the drawing fades out towards its edges
        .mask(RadialGradient(colors: [.black, .black, .clear], center: .center, startRadius: 0, endRadius: 100))
    }
}

/// Title outside, one glass card with rows inside (design.md §8).
struct CardSection<Content: View>: View {
    let title: String?
    var logo: URL? = nil
    @ViewBuilder let content: Content

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            if let title { SectionTitle(title, logo: logo) }
            VStack(spacing: 0) { content }.glassCard()
        }
    }
}

/// A section's title above its card.
struct SectionTitle: View {
    let title: String
    var logo: URL? = nil

    init(_ title: String, logo: URL? = nil) {
        self.title = title
        self.logo = logo
    }

    var body: some View {
        HStack(spacing: 8) {
            if let logo { Logo(url: logo, size: 20, label: title) }
            Text(title).font(.subheadline.weight(.semibold)).foregroundStyle(Color.textSecondary)
        }
        .padding(.horizontal, 4)
        .accessibilityAddTraits(.isHeader)
    }
}

/// Goals and assists in a match: a ball and a boot, each with its count; nothing when there are none.
struct Contributions: View {
    let goals: Int
    let assists: Int
    var size: CGFloat = 12

    var body: some View {
        if goals > 0 || assists > 0 {
            HStack(spacing: size / 2) {
                if goals > 0 { item("soccerball", goals) }
                if assists > 0 { item("shoe.fill", assists) }
            }
            .foregroundStyle(Color.textPrimary)
            .accessibilityElement(children: .ignore)
            .accessibilityLabel(Self.spoken(goals: goals, assists: assists))
        }
    }

    private func item(_ symbol: String, _ count: Int) -> some View {
        HStack(spacing: 1) {
            Image(systemName: symbol).font(.system(size: size * 0.9, weight: .semibold))
            Text("\(count)").font(.digits(size + 1, relativeTo: .caption2))
        }
    }

    /// "2 goals, 1 assist"
    static func spoken(goals: Int, assists: Int) -> String {
        [goals > 0 ? "\(goals) \(goals == 1 ? "goal" : "goals")" : nil,
         assists > 0 ? "\(assists) \(assists == 1 ? "assist" : "assists")" : nil].compactMap { $0 }.joined(separator: ", ")
    }
}

// Loading skeletons (design.md §8): soft bars and circles in the shape of the data that is coming, under one slow
// highlight that sweeps down the screen. They replace the spinner everywhere a screen or a tab loads.

extension View {
    /// A soft band of light sweeping across the view, masked to its shapes; still under Reduce Motion.
    func shimmer() -> some View { modifier(Shimmer()) }
}

private struct Shimmer: ViewModifier {
    @State private var moving = false
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    func body(content: Content) -> some View {
        content
            .overlay {
                GeometryReader { geo in
                    LinearGradient(colors: [.clear, .white.opacity(0.10), .clear], startPoint: .top, endPoint: .bottom)
                        .frame(height: 240)
                        .offset(y: moving ? geo.size.height : -240)
                }
                .mask(content)
                .allowsHitTesting(false)
                .opacity(reduceMotion ? 0 : 1)
            }
            .onAppear {
                guard !reduceMotion else { return }
                withAnimation(.linear(duration: 1.4).repeatForever(autoreverses: false)) { moving = true }
            }
            .accessibilityElement(children: .ignore)
            .accessibilityLabel("Loading")
    }
}

struct SkeletonBar: View {
    var width: CGFloat? = nil  // nil: as wide as it may be
    var height: CGFloat = 12

    var body: some View {
        RoundedRectangle(cornerRadius: height / 2, style: .continuous)
            .fill(Color.skeleton)
            .frame(width: width, height: height)
            .frame(maxWidth: width == nil ? .infinity : nil, alignment: .leading)
    }
}

struct SkeletonCircle: View {
    let size: CGFloat

    var body: some View {
        Circle().fill(Color.skeleton).frame(width: size, height: size)
    }
}

/// A row like a list row: an image, one or two lines, a short value on the right.
struct SkeletonRow: View {
    var image: CGFloat = 24
    var lines = 1
    var trailing = true

    var body: some View {
        HStack(spacing: 12) {
            SkeletonCircle(size: image)
            VStack(alignment: .leading, spacing: 6) {
                SkeletonBar(width: 150)
                if lines > 1 { SkeletonBar(width: 90, height: 10) }
            }
            Spacer(minLength: 8)
            if trailing { SkeletonBar(width: 24) }
        }
        .padding(.horizontal, 16)
        .frame(minHeight: 52)
    }
}

/// A row like `MatchRow`: time on the left, two teams with their scores.
struct SkeletonMatchRow: View {
    var body: some View {
        HStack(spacing: 8) {
            SkeletonBar(width: 36, height: 10).frame(width: 46, alignment: .leading)
            VStack(spacing: 10) {
                ForEach(0..<2, id: \.self) { _ in
                    HStack(spacing: 10) {
                        SkeletonCircle(size: 24)
                        SkeletonBar(width: 120)
                        Spacer()
                        SkeletonBar(width: 12, height: 16)
                    }
                }
            }
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 12)
    }
}

/// A titled glass card of rows, like `CardSection`.
struct SkeletonCard<Row: View>: View {
    var title = true
    var rows = 4
    @ViewBuilder var row: () -> Row

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            if title { SkeletonBar(width: 120).padding(.horizontal, 4).padding(.vertical, 3) }
            VStack(spacing: 0) {
                ForEach(0..<rows, id: \.self) { index in
                    if index > 0 { Hairline() }
                    row()
                }
            }
            .glassCard()
        }
    }
}

/// Label on the left, value on the right, like `FactsCard`.
struct SkeletonFacts: View {
    var rows = 4

    var body: some View {
        VStack(spacing: 0) {
            ForEach(0..<rows, id: \.self) { index in
                if index > 0 { Hairline() }
                HStack {
                    SkeletonBar(width: 70)
                    Spacer()
                    SkeletonBar(width: 110)
                }
                .padding(.horizontal, 16)
                .frame(minHeight: 44)
            }
        }
        .glassCard()
    }
}

/// The tab picker's empty track.
struct SkeletonTabs: View {
    var body: some View {
        GlassBackground(shape: Capsule()).frame(height: 52)
    }
}

// MARK: - Screens

struct MatchSkeleton: View {
    var body: some View {
        VStack(spacing: 24) {
            VStack(spacing: 12) {
                SkeletonBar(width: 190).padding(.horizontal, 4).frame(minHeight: 44)
                HStack(alignment: .top) {
                    team
                    Spacer()
                    SkeletonBar(width: 96, height: 40).padding(.top, 12)
                    Spacer()
                    team
                }
                .padding(16)
                .glassCard()
                VStack(spacing: 0) {
                    ForEach(0..<2, id: \.self) { index in
                        if index > 0 { Hairline() }
                        HStack { SkeletonBar(width: 80); Spacer(); SkeletonBar(width: 40); Spacer(); SkeletonBar(width: 80) }
                            .padding(.horizontal, 16)
                            .frame(minHeight: 40)
                    }
                }
                .glassCard()
            }
            SkeletonTabs()
            SkeletonCard(title: false, rows: 6) { SkeletonRow(lines: 2, trailing: false) }
        }
        .shimmer()
    }

    private var team: some View {
        VStack(spacing: 8) {
            SkeletonCircle(size: 64)
            SkeletonBar(width: 76)
        }
    }
}

/// A player's or a club's page: the big image, the name, the facts, the tabs, a list.
struct ProfileSkeleton: View {
    var image: CGFloat = 96
    var facts = 5

    var body: some View {
        VStack(spacing: 24) {
            VStack(spacing: 14) {
                SkeletonCircle(size: image)
                SkeletonBar(width: 160, height: 20)
                SkeletonBar(width: 90, height: 12)
            }
            SkeletonFacts(rows: facts)
            SkeletonTabs()
            SkeletonCard(title: false, rows: 4) { SkeletonMatchRow() }
        }
        .shimmer()
    }
}

/// A standings table: position, crest, team, figures.
struct TableSkeleton: View {
    var body: some View {
        VStack(spacing: 0) {
            ForEach(0..<12, id: \.self) { index in
                if index > 0 { Hairline() }
                HStack(spacing: 8) {
                    SkeletonBar(width: 14).frame(width: 24, alignment: .leading)
                    SkeletonCircle(size: 24)
                    SkeletonBar(width: 130)
                    Spacer()
                    SkeletonBar(width: 18)
                    SkeletonBar(width: 22)
                    SkeletonBar(width: 22)
                }
                .padding(.horizontal, 16)
                .frame(minHeight: 44)
            }
        }
        .glassCard()
        .shimmer()
    }
}

/// Rounds or competitions of matches: titled cards of match rows.
struct MatchListSkeleton: View {
    var sections = 2

    var body: some View {
        VStack(spacing: 32) {
            ForEach(0..<sections, id: \.self) { _ in
                SkeletonCard(rows: 3) { SkeletonMatchRow() }
            }
        }
        .shimmer()
    }
}
