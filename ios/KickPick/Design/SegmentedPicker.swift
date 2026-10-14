import SwiftUI

/// Glass track with a raised white pill on the selected segment (design.md §6.2).
/// With `icons` (SF Symbols, one per option) it is the app's tab bar. `draggable`: the pill can also be dragged
/// like the native iOS 26 tab bar — it follows the finger and selects the segment it is dropped on.
struct SegmentedPicker<Value: Hashable>: View {
    let options: [(value: Value, title: String)]
    @Binding var selection: Value
    var icons: [String] = []
    // shortcut: drag only where there is no scroll view around — it would swallow vertical scrolls started on
    // the picker; a UIKit pan that begins only on horizontal moves would lift that (iOS 18+)
    var draggable = false
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
        .highPriorityGesture(drag, including: draggable ? .all : .subviews)  // wins over the segment buttons
        .sensoryFeedback(.selection, trigger: highlighted)
        .padding(4)
        .background(GlassBackground(shape: Capsule()))
    }

    private func index(at x: CGFloat) -> Int {
        min(max(Int(x / (segment + Self.spacing)), 0), options.count - 1)
    }

    private var drag: some Gesture {
        DragGesture(minimumDistance: 8)
            .onChanged { value in
                withAnimation(reduceMotion ? nil : .interactiveSpring(response: 0.25, dampingFraction: 0.8)) {
                    dragX = value.location.x
                }
            }
            .onEnded { _ in
                guard let dragX else { return }
                let target = options[index(at: dragX)].value
                withAnimation(reduceMotion ? nil : .spring(response: 0.3, dampingFraction: 0.8)) {
                    self.dragX = nil
                    selection = target
                }
            }
    }
}
