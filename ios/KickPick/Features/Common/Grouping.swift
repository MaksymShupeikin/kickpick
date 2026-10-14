import Foundation

struct Grouped<Key: Hashable, Item>: Identifiable {
    let key: Key
    let items: [Item]
    var id: Key { key }
}

extension Array {
    /// Groups in first-appearance order.
    func grouped<Key: Hashable>(by key: (Element) -> Key) -> [Grouped<Key, Element>] {
        var order: [Key] = []
        var groups: [Key: [Element]] = [:]
        for element in self {
            let k = key(element)
            if groups[k] == nil { order.append(k) }
            groups[k, default: []].append(element)
        }
        return order.map { Grouped(key: $0, items: groups[$0]!) }
    }
}

func roundTitle(_ round: String) -> String {
    switch round {
    case "playoff": return "Play-off round"
    case "1/4": return "Quarter-finals"
    case "1/2": return "Semi-finals"
    case "bronze": return "Third-place play-off"
    case "final": return "Final"
    default:
        if round.hasPrefix("1/"), let n = Int(round.dropFirst(2)) { return "Round of \(2 * n)" }  // 1/8 → Round of 16
        return Int(round) != nil ? "Matchday \(round)" : round
    }
}
