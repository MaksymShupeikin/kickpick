import SwiftUI

/// Loads a value and shows it; offers a retry on failure; while `live(value)` is true, reloads every 30 s.
struct Loader<Value, Content: View>: View {
    var id: AnyHashable = 0
    var placeholder: Value? = nil
    var live: (Value) -> Bool = { _ in false }
    let load: () async throws -> Value
    @ViewBuilder let content: (Value) -> Content

    @State private var value: Value?
    @State private var loadedID: AnyHashable?
    @State private var failed = false
    @State private var attempt = 0

    var body: some View {
        Group {
            if let value {
                content(value)
            } else if failed {
                ErrorState { failed = false; attempt += 1 }
            } else if let placeholder {
                content(placeholder).redacted(reason: .placeholder).disabled(true)
            } else {
                ProgressView().frame(maxWidth: .infinity, minHeight: 240)
            }
        }
        .task(id: [id, AnyHashable(attempt)]) {
            if loadedID != id { value = nil }
            await reload()
            loadedID = id
            while let current = value, live(current), !Task.isCancelled {
                try? await Task.sleep(for: .seconds(30))
                await reload()
            }
        }
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
