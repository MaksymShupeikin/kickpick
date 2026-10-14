import SwiftUI

/// Glass track with a raised white pill on the selected segment (design.md §6.2).
/// With `icons` (SF Symbols, one per option) it is the app's tab bar.
struct SegmentedPicker<Value: Hashable>: View {
    let options: [(value: Value, title: String)]
    @Binding var selection: Value
    var icons: [String] = []
    @Namespace private var namespace
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    var body: some View {
        HStack(spacing: 4) {
            ForEach(options.indices, id: \.self) { index in
                let option = options[index]
                let selected = option.value == selection
                Button {
                    withAnimation(reduceMotion ? nil : .easeInOut(duration: 0.2)) { selection = option.value }
                } label: {
                    VStack(spacing: 2) {
                        if index < icons.count {
                            Image(systemName: icons[index]).font(.system(size: 18, weight: .semibold)).accessibilityHidden(true)
                        }
                        Text(option.title).font(icons.isEmpty ? .subheadline.weight(.semibold) : .caption2.weight(.semibold))
                    }
                    .foregroundStyle(selected ? Color.onAccent : Color.textSecondary)
                    .lineLimit(1)
                    .frame(maxWidth: .infinity, minHeight: icons.isEmpty ? 44 : 52)
                    .background {
                        if selected { RaisedCapsule().matchedGeometryEffect(id: "selection", in: namespace) }
                    }
                    .contentShape(Capsule())
                }
                .buttonStyle(.plain)
                .accessibilityAddTraits(selected ? .isSelected : [])
            }
        }
        .padding(4)
        .background(GlassBackground(shape: Capsule()))
    }
}
