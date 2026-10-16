import SwiftUI

/// Glass track with a raised white pill on the selected segment (design.md §6.2).
/// Tap a segment, or slide the pill like the native iOS 26 tab bar: it follows the finger and selects the segment
/// it is dropped on. With `icons` (SF Symbols, one per option) it is the app's tab bar. With `scrolls`, titles that
/// don't fit side by side keep their width in a scrolling track, which follows the selection and the dragged pill.
struct SegmentedPicker<Value: Hashable>: View {
    let options: [(value: Value, title: String)]
    @Binding var selection: Value
    var icons: [String] = []
    var captions: [String] = []  // a small line above each title ("Today", "Thu")
    var scrolls = false
    @State private var width: CGFloat = 0
    @State private var dragX: CGFloat?  // finger position while the pill is dragged
    @State private var frames: [Int: CGRect] = [:]  // scrolling segments, in the track's space
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    private static var spacing: CGFloat { 4 }
    private static var track: String { "SegmentedPicker.track" }
    private var segment: CGFloat {
        max((width - Self.spacing * CGFloat(options.count - 1)) / CGFloat(options.count), 0)
    }
    private var selectedIndex: Int { options.firstIndex { $0.value == selection } ?? 0 }
    /// The segment under the pill: where the finger is while dragging, otherwise the selection.
    private var highlighted: Int { dragX.map(index(at:)) ?? selectedIndex }
    private var pillOffset: CGFloat {
        if let dragX { return min(max(dragX - segment / 2, 0), width - segment) }
        return CGFloat(selectedIndex) * (segment + Self.spacing)
    }

    var body: some View {
        if scrolls && options.count > 5 {
            scrolling  // more than a phone fits side by side (and ViewThatFits would size every title × every title)
        } else if scrolls {
            ViewThatFits(in: .horizontal) { fixed; scrolling }
        } else {
            fixed
        }
    }

    /// Equal segments across the track.
    private var fixed: some View {
        HStack(spacing: Self.spacing) {
            ForEach(options.indices, id: \.self) { button($0, highlighted: highlighted, stretches: true) }
        }
        .background(alignment: .leading) {
            RaisedCapsule()
                .frame(width: segment)
                .scaleEffect(dragX == nil || reduceMotion ? 1 : 1.06)  // lifted while held, like the native lens
                .offset(x: pillOffset)
        }
        .onGeometryChange(for: CGFloat.self) { $0.size.width } action: { width = $0 }
        .horizontalPan { x in
            withAnimation(reduceMotion ? nil : .interactiveSpring(response: 0.25, dampingFraction: 0.8)) { dragX = x }
        } ended: { x in
            drop(x.map { options[index(at: $0)].value })
        }
        .sensoryFeedback(.selection, trigger: highlighted)
        .padding(4)
        .background(GlassBackground(shape: Capsule()))
    }

    /// Segments as wide as their titles in a horizontal scroll. The pill is dragged only from where it is
    /// (anywhere else the track scrolls); its next segment scrolls into view as it moves, and a new selection
    /// is centred.
    private var scrolling: some View {
        let current = dragX.map(nearest(to:)) ?? selectedIndex
        return ScrollViewReader { proxy in
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: Self.spacing) {
                    ForEach(options.indices, id: \.self) { index in
                        button(index, highlighted: current, stretches: false)
                            .onGeometryChange(for: CGRect.self) { $0.frame(in: .named(Self.track)) } action: {
                                frames[index] = $0
                            }
                            .id(index)
                    }
                }
                .background(alignment: .topLeading) {
                    if let pill = pill(over: current) {
                        RaisedCapsule()
                            .frame(width: pill.width, height: pill.height)
                            .scaleEffect(dragX == nil || reduceMotion ? 1 : 1.06)
                            .offset(x: pill.minX, y: pill.minY)
                    }
                }
                .coordinateSpace(.named(Self.track))
                .horizontalPan(startsAt: { x in pill(over: current).map { ($0.minX - 8...$0.maxX + 8).contains(x) } ?? false }) { x in
                    withAnimation(reduceMotion ? nil : .interactiveSpring(response: 0.25, dampingFraction: 0.8)) { dragX = x }
                } ended: { x in
                    drop(x.map { options[nearest(to: $0)].value })
                }
                .padding(4)
            }
            .onAppear { proxy.scrollTo(selectedIndex, anchor: .center) }
            .onChange(of: selectedIndex) { _, index in reveal(index, anchor: .center, proxy) }
            .onChange(of: current) { old, new in
                guard dragX != nil, new != old else { return }
                reveal(min(max(new + (new > old ? 1 : -1), 0), options.count - 1), anchor: nil, proxy)
            }
        }
        .sensoryFeedback(.selection, trigger: current)
        .clipShape(Capsule())
        .background(GlassBackground(shape: Capsule()))
    }

    private func button(_ index: Int, highlighted: Int, stretches: Bool) -> some View {
        let option = options[index]
        return Button {
            withAnimation(reduceMotion ? nil : .easeInOut(duration: 0.2)) { selection = option.value }
        } label: {
            VStack(spacing: 2) {
                if index < icons.count {
                    Image(systemName: icons[index]).font(.system(size: 18, weight: .semibold)).accessibilityHidden(true)
                }
                if index < captions.count {
                    Text(captions[index]).font(.caption2.weight(.medium)).opacity(0.75)
                }
                ZStack {
                    // equal segments size to the longest title, so ViewThatFits only keeps them when every title fits
                    if scrolls && stretches {
                        ForEach(options.indices, id: \.self) { Text(options[$0].title).hidden() }.accessibilityHidden(true)
                    }
                    Text(option.title)
                }
                .font(icons.isEmpty ? .subheadline.weight(.semibold) : .caption2.weight(.semibold))
            }
            .foregroundStyle(index == highlighted ? Color.onAccent : Color.textSecondary)
            .lineLimit(1)
            .padding(.horizontal, scrolls ? 16 : 0)
            .frame(maxWidth: stretches ? .infinity : nil, minHeight: icons.isEmpty && captions.isEmpty ? 44 : 52)
            .contentShape(Capsule())
        }
        .buttonStyle(.plain)
        .accessibilityAddTraits(option.value == selection ? .isSelected : [])
    }

    private func drop(_ target: Value?) {
        withAnimation(reduceMotion ? nil : .spring(response: 0.3, dampingFraction: 0.8)) {
            dragX = nil
            selection = target ?? selection  // nil: the pan was cancelled
        }
    }

    /// The scrolling pill: over segment `index`, or under the finger while dragged, kept inside the track.
    private func pill(over index: Int) -> CGRect? {
        guard var frame = frames[index] else { return nil }
        if let dragX, let end = frames.values.map(\.maxX).max() {
            frame.origin.x = min(max(dragX - frame.width / 2, 0), end - frame.width)
        }
        return frame
    }

    private func nearest(to x: CGFloat) -> Int {
        frames.min { abs($0.value.midX - x) < abs($1.value.midX - x) }?.key ?? selectedIndex
    }

    private func reveal(_ index: Int, anchor: UnitPoint?, _ proxy: ScrollViewProxy) {
        withAnimation(reduceMotion ? nil : .easeInOut(duration: 0.25)) { proxy.scrollTo(index, anchor: anchor) }
    }

    private func index(at x: CGFloat) -> Int {
        min(max(Int(x / (segment + Self.spacing)), 0), options.count - 1)
    }
}

/// A pan that only starts on a mostly horizontal move, so a vertical swipe begun on the picker still scrolls
/// the page around it. SwiftUI's DragGesture can't decline by direction: it either swallows the scroll or loses
/// to the segment buttons. With `startsAt`, it also starts only where that accepts the touch-down x, and scroll
/// views wait for it, so a drag there moves the pill instead of scrolling.
@available(iOS 18, *)
private struct HorizontalPan: UIGestureRecognizerRepresentable {
    let startsAt: ((CGFloat) -> Bool)?
    let changed: (CGFloat) -> Void
    let ended: (CGFloat?) -> Void

    func makeUIGestureRecognizer(context: Context) -> UIPanGestureRecognizer {
        let pan = UIPanGestureRecognizer()
        pan.delegate = context.coordinator
        return pan
    }

    func updateUIGestureRecognizer(_ pan: UIPanGestureRecognizer, context: Context) {
        context.coordinator.startsAt = startsAt
    }

    func handleUIGestureRecognizerAction(_ pan: UIPanGestureRecognizer, context: Context) {
        switch pan.state {
        case .began, .changed: changed(context.converter.localLocation.x)
        case .ended: ended(context.converter.localLocation.x)
        case .cancelled, .failed: ended(nil)
        default: break
        }
    }

    func makeCoordinator(converter: CoordinateSpaceConverter) -> Coordinator { Coordinator(converter: converter) }

    final class Coordinator: NSObject, UIGestureRecognizerDelegate {
        let converter: CoordinateSpaceConverter
        var startsAt: ((CGFloat) -> Bool)?

        init(converter: CoordinateSpaceConverter) { self.converter = converter }

        func gestureRecognizerShouldBegin(_ recognizer: UIGestureRecognizer) -> Bool {
            guard let pan = recognizer as? UIPanGestureRecognizer else { return true }
            let velocity = pan.velocity(in: pan.view)
            guard abs(velocity.x) > abs(velocity.y) else { return false }
            let start = converter.localLocation.x - (converter.localTranslation?.x ?? 0)  // where the finger went down
            return startsAt?(start) ?? true
        }

        func gestureRecognizer(_ recognizer: UIGestureRecognizer,
                               shouldBeRequiredToFailBy other: UIGestureRecognizer) -> Bool {
            startsAt != nil && other.view is UIScrollView
        }
    }
}

extension View {
    /// A horizontal drag that leaves vertical scrolling alone: `changed` gets the finger's x, `ended` the last x
    /// (nil when cancelled).
    // shortcut: iOS 17 has no UIGestureRecognizerRepresentable, so there the pickers are tap-only and days don't swipe
    @ViewBuilder func horizontalPan(startsAt: ((CGFloat) -> Bool)? = nil, changed: @escaping (CGFloat) -> Void,
                                    ended: @escaping (CGFloat?) -> Void) -> some View {
        if #available(iOS 18, *) { gesture(HorizontalPan(startsAt: startsAt, changed: changed, ended: ended)) } else { self }
    }
}
