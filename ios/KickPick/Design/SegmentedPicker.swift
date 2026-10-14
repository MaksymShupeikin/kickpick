import SwiftUI

/// Glass track with a raised white pill on the selected segment (design.md §6.2).
/// Tap a segment, or slide the pill like the native iOS 26 tab bar: it follows the finger and selects the segment
/// it is dropped on. With `icons` (SF Symbols, one per option) it is the app's tab bar.
struct SegmentedPicker<Value: Hashable>: View {
    let options: [(value: Value, title: String)]
    @Binding var selection: Value
    var icons: [String] = []
    @State private var width: CGFloat = 0
    @State private var dragX: CGFloat?  // finger position while the pill is dragged
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    private static var spacing: CGFloat { 4 }
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
        HStack(spacing: Self.spacing) {
            ForEach(options.indices, id: \.self) { index in
                let option = options[index]
                Button {
                    withAnimation(reduceMotion ? nil : .easeInOut(duration: 0.2)) { selection = option.value }
                } label: {
                    VStack(spacing: 2) {
                        if index < icons.count {
                            Image(systemName: icons[index]).font(.system(size: 18, weight: .semibold)).accessibilityHidden(true)
                        }
                        Text(option.title).font(icons.isEmpty ? .subheadline.weight(.semibold) : .caption2.weight(.semibold))
                    }
                    .foregroundStyle(index == highlighted ? Color.onAccent : Color.textSecondary)
                    .lineLimit(1)
                    .frame(maxWidth: .infinity, minHeight: icons.isEmpty ? 44 : 52)
                    .contentShape(Capsule())
                }
                .buttonStyle(.plain)
                .accessibilityAddTraits(option.value == selection ? .isSelected : [])
            }
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
            let target = x.map { options[index(at: $0)].value } ?? selection  // nil: the pan was cancelled
            withAnimation(reduceMotion ? nil : .spring(response: 0.3, dampingFraction: 0.8)) {
                dragX = nil
                selection = target
            }
        }
        .sensoryFeedback(.selection, trigger: highlighted)
        .padding(4)
        .background(GlassBackground(shape: Capsule()))
    }

    private func index(at x: CGFloat) -> Int {
        min(max(Int(x / (segment + Self.spacing)), 0), options.count - 1)
    }
}

/// A pan that only starts on a mostly horizontal move, so a vertical swipe begun on the picker still scrolls
/// the page around it. SwiftUI's DragGesture can't decline by direction: it either swallows the scroll or loses
/// to the segment buttons.
@available(iOS 18, *)
private struct HorizontalPan: UIGestureRecognizerRepresentable {
    let changed: (CGFloat) -> Void
    let ended: (CGFloat?) -> Void

    func makeUIGestureRecognizer(context: Context) -> UIPanGestureRecognizer {
        let pan = UIPanGestureRecognizer()
        pan.delegate = context.coordinator
        return pan
    }

    func handleUIGestureRecognizerAction(_ pan: UIPanGestureRecognizer, context: Context) {
        switch pan.state {
        case .began, .changed: changed(context.converter.localLocation.x)
        case .ended: ended(context.converter.localLocation.x)
        case .cancelled, .failed: ended(nil)
        default: break
        }
    }

    func makeCoordinator(converter: CoordinateSpaceConverter) -> Coordinator { Coordinator() }

    final class Coordinator: NSObject, UIGestureRecognizerDelegate {
        func gestureRecognizerShouldBegin(_ recognizer: UIGestureRecognizer) -> Bool {
            guard let pan = recognizer as? UIPanGestureRecognizer else { return true }
            let velocity = pan.velocity(in: pan.view)
            return abs(velocity.x) > abs(velocity.y)
        }
    }
}

private extension View {
    // shortcut: iOS 17 has no UIGestureRecognizerRepresentable, so there the pickers are tap-only
    @ViewBuilder func horizontalPan(changed: @escaping (CGFloat) -> Void, ended: @escaping (CGFloat?) -> Void) -> some View {
        if #available(iOS 18, *) { gesture(HorizontalPan(changed: changed, ended: ended)) } else { self }
    }
}
