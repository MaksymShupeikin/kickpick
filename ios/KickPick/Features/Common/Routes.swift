import SwiftUI

enum Route: Hashable {
    case competition(Competition, season: String? = nil)  // nil: the current season
    case match(Int)
    case team(Int)
    case player(Int)
}

extension View {
    func withRoutes() -> some View {
        navigationDestination(for: Route.self) { route in
            Group {
                switch route {
                case .competition(let competition, let season): CompetitionView(competition: competition, season: season)
                case .match(let id): MatchView(id: id)
                case .team(let id): TeamView(id: id)
                case .player(let id): PlayerView(id: id)
                }
            }
            .glassBackButton()
        }
    }
}
