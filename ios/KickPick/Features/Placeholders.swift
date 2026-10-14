import SwiftUI

struct CompetitionsView: View { var body: some View { Text("Турниры") } }
struct SearchView: View { var body: some View { Text("Поиск") } }
struct CompetitionView: View { let competition: Competition; var body: some View { Text(competition.name) } }
struct TeamView: View { let id: Int; var body: some View { Text("\(id)") } }
struct PlayerView: View { let id: Int; var body: some View { Text("\(id)") } }
