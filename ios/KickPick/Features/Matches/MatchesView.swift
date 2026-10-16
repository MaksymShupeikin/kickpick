import SwiftUI

struct MatchesView: View {
    @State private var day = Calendar.current.startOfDay(for: .now)
    @State private var pickingDate = false
    @State private var calendarPicks = 0
    @State private var calendarHeight: CGFloat = 520
    @State private var forward = true  // which way the day last moved: the list slides in from that side
    @State private var swipeStart: CGFloat?
    @State private var loaded: [Date: [Match]] = [:]  // days seen this session: shown at once, refreshed behind
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    var body: some View {
        SearchableScreen {
            HStack(spacing: 8) {  // fixed under the search field: the day stays in reach while the list scrolls
                SegmentedPicker(options: days.map { ($0.value, $0.title) },
                                selection: Binding(get: { day }, set: { go(to: $0) }),
                                captions: days.map(\.caption), scrolls: true)
                    // a fresh strip, centred on the picked day, after every calendar pick: rebuilt around a far date,
                    // the picked day keeps the centre index, so a strip scrolled away by hand wouldn't move back
                    .id(calendarPicks)
                Button { pickingDate = true } label: { Image(systemName: "calendar") }
                    .buttonStyle(.glassIcon)
                    .accessibilityLabel("Choose date")
            }
        } content: {
            VStack {  // a swipe sideways moves a day, like turning a page: finger left, the next day
                Loader(id: day, cached: loaded[day], placeholder: Match.placeholders,
                       live: { $0.contains { $0.needsPolling } }) {
                    try await load(day)
                } content: { matches in
                    if matches.isEmpty {
                        EmptyState(text: "No matches")
                    } else {
                        VStack(alignment: .leading, spacing: 32) {
                            ForEach(matches.grouped(by: \.competition.slug)) { group in
                                let competition = group.items[0].competition
                                CardSection(title: competition.name, logo: competition.logoUrl) {
                                    Rows(items: group.items) { match in
                                        NavigationLink(value: Route.match(match.id)) { MatchRow(match: match, showDate: false) }
                                            .buttonStyle(.plain)
                                    }
                                }
                            }
                        }
                    }
                }
                .id(day)
                .transition(reduceMotion ? .opacity : .asymmetric(insertion: .move(edge: forward ? .trailing : .leading),
                                                                  removal: .move(edge: forward ? .leading : .trailing)))
            }
            .frame(maxWidth: .infinity, minHeight: 480, alignment: .top)  // swipeable below a short list too
            .contentShape(Rectangle())
            .horizontalPan { x in
                if swipeStart == nil { swipeStart = x }
            } ended: { x in
                defer { swipeStart = nil }
                guard let x, let start = swipeStart, abs(x - start) > 60 else { return }
                go(to: Calendar.current.date(byAdding: .day, value: x < start ? 1 : -1, to: day)!)
            }
        }
        .task(id: day) {  // two days either side, so even quick swipes land on a ready list
            for offset in [1, -1, 2, -2] {
                let neighbour = Calendar.current.date(byAdding: .day, value: offset, to: day)!
                if loaded[neighbour] == nil { _ = try? await load(neighbour) }
            }
        }
        .sheet(isPresented: $pickingDate) {
            VStack(spacing: 8) {
                HStack {
                    if !Calendar.current.isDateInToday(day) {  // a way back from wherever the calendar went
                        Button("Today") { choose(.now) }.buttonStyle(.glass)
                    }
                    Spacer()
                    Button { pickingDate = false } label: { Image(systemName: "xmark") }
                        .buttonStyle(.glassIcon)  // like the back and calendar buttons
                        .accessibilityLabel("Close")
                }
                .frame(minHeight: 44)  // the same height with or without "Today"
                .padding(.horizontal, 8)  // clear of the sheet's rounded corners
                CalendarPicker(selected: day) { choose($0) }
            }
            .padding(.horizontal)
            .padding(.top, 24)
            .padding(.bottom)
            .fixedSize(horizontal: false, vertical: true)
            .onGeometryChange(for: CGFloat.self) { $0.size.height } action: { calendarHeight = $0 }
            .presentationDetents([.height(calendarHeight)])  // as tall as the buttons and the month (5 or 6 weeks)
        }
        .sensoryFeedback(.selection, trigger: calendarPicks)  // a day picked in the calendar, like a tick in the strip
    }

    private func load(_ date: Date) async throws -> [Match] {
        let matches = try await APIClient.shared.matches(from: date, to: Calendar.current.date(byAdding: .day, value: 1, to: date)!)
        loaded[date] = matches
        return matches
    }

    private func choose(_ date: Date) {
        go(to: date)
        calendarPicks += 1
        pickingDate = false
    }

    /// Every change of day: strip, swipe, calendar. The direction is set first, so the list knows where to slide.
    private func go(to date: Date) {
        let target = Calendar.current.startOfDay(for: date)
        guard target != day else { return }
        forward = target > day
        withAnimation(reduceMotion ? nil : .easeInOut(duration: 0.25)) { day = target }
    }

    /// A month back and a month ahead of today ("Today" / "15 Oct", "Thu" / "16 Oct" …, the year on days of
    /// another year: "5 Dec 2025"); around the picked day
    /// instead when the calendar picked one further away.
    private var days: [(value: Date, title: String, caption: String)] {
        let calendar = Calendar.current
        let today = calendar.startOfDay(for: .now)
        let distance = abs(calendar.dateComponents([.day], from: today, to: day).day ?? 0)
        let anchor = distance > Self.reach ? day : today
        let relative = [-1: "Yesterday", 0: "Today", 1: "Tomorrow"]
        return (-Self.reach...Self.reach).map { offset in
            let date = calendar.date(byAdding: .day, value: offset, to: anchor)!
            let fromToday = calendar.dateComponents([.day], from: today, to: date).day ?? 0
            var style = Date.FormatStyle.dateTime.day().month(.abbreviated).locale(.app)
            if !calendar.isDate(date, equalTo: today, toGranularity: .year) { style = style.year() }  // "5 Dec 2025"
            return (date, date.formatted(style),
                    relative[fromToday] ?? date.formatted(.dateTime.weekday(.abbreviated).locale(.app)))
        }
    }

    private static let reach = 30
}

/// UIKit's calendar: its selection changes only when a day is tapped, so choosing a month or year in the header
/// keeps it open (a graphical DatePicker changes its date, and so closed the sheet, as soon as the month changed).
private struct CalendarPicker: UIViewRepresentable {
    let selected: Date
    let pick: (Date) -> Void

    func makeUIView(context: Context) -> UICalendarView {
        let view = UICalendarView()
        view.calendar = .current
        view.locale = .app
        view.tintColor = .white
        let day = Calendar.current.dateComponents([.year, .month, .day], from: selected)
        let selection = UICalendarSelectionSingleDate(delegate: context.coordinator)
        selection.selectedDate = day
        view.selectionBehavior = selection
        view.visibleDateComponents = day
        view.setContentHuggingPriority(.required, for: .vertical)
        return view
    }

    func updateUIView(_ view: UICalendarView, context: Context) {}

    func makeCoordinator() -> Coordinator { Coordinator(pick: pick) }

    // shortcut: tapping the day that's already selected does nothing (UIKit doesn't report it); the sheet closes with
    // a swipe or a tap outside, as system calendars do. Mark the day with a decoration instead if that bothers anyone
    final class Coordinator: NSObject, UICalendarSelectionSingleDateDelegate {
        let pick: (Date) -> Void

        init(pick: @escaping (Date) -> Void) { self.pick = pick }

        func dateSelection(_ selection: UICalendarSelectionSingleDate, didSelectDate day: DateComponents?) {
            if let day, let date = Calendar.current.date(from: day) { pick(date) }
        }
    }
}
