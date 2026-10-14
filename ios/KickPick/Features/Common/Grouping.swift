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
    case "playoff": return "Раунд плей-офф"
    case "1/2": return "Полуфинал"
    case "bronze": return "Матч за 3-е место"
    case "final": return "Финал"
    default:
        if round.hasPrefix("1/") { return "\(round) финала" }
        return Int(round) != nil ? "Тур \(round)" : round
    }
}
