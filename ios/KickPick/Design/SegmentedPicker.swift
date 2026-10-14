import SwiftUI

/// Glass track with a raised white pill on the selected segment (design.md §6.2).
struct SegmentedPicker<Value: Hashable>: View {
    let options: [(value: Value, title: String)]
    @Binding var selection: Value
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
                    Text(option.title)
                        .font(.subheadline.weight(.semibold))
                        .foregroundStyle(selected ? Color.onAccent : Color.textSecondary)
                        .lineLimit(1)
                        .frame(maxWidth: .infinity, minHeight: 44)
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
