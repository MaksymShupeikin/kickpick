import SwiftUI

/// Loads a value and shows it; offers a retry on failure; while `live(value)` is true, reloads every 15 s (the
/// collector checks live scores as often; an unchanged answer comes back as an empty 304).
/// With `cached`, that is shown as is while the fresh value loads (no placeholder, no flash).
struct Loader<Value, Content: View>: View {
    var id: AnyHashable = 0
    var cached: Value? = nil
    var placeholder: Value? = nil
    var skeleton: AnyView? = nil  // the shape of what's coming; a list of rows when none is given
    var live: (Value) -> Bool = { _ in false }
    var refreshEvery: ((Value) -> Duration?)? = nil
    let load: () async throws -> Value
    @ViewBuilder let content: (Value) -> Content

    @State private var value: Value?
    @State private var loadedID: AnyHashable?
    @State private var failed = false
    @State private var attempt = 0

    var body: some View {
        Group {
            if let value = value ?? cached {
                content(value)
            } else if failed {
                ErrorState { failed = false; attempt += 1 }
            } else if let placeholder {
                content(placeholder).redacted(reason: .placeholder).disabled(true).shimmer()
            } else {
                skeleton ?? AnyView(SkeletonCard(title: false, rows: 6) { SkeletonRow() }.shimmer())
            }
        }
        .sensoryFeedback(.error, trigger: failed) { _, failed in failed }  // "Couldn't load" appeared
        .task(id: [id, AnyHashable(attempt)]) {
            if loadedID != id { value = nil }
            await reload()
            loadedID = id
            while let current = value, let delay = refreshDelay(current), !Task.isCancelled {
                do { try await Task.sleep(for: delay) } catch { return }
                await reload()
            }
        }
    }

    private func refreshDelay(_ value: Value) -> Duration? {
        if let refreshEvery { return refreshEvery(value) }
        return live(value) ? .seconds(15) : nil
    }

    private func reload() async {
        do {
            value = try await load()
            failed = false
        } catch is CancellationError {
        } catch let error as URLError where error.code == .cancelled {
        } catch {
            if value == nil { failed = true }
        }
    }
}
