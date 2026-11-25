struct Orders {
    let items: [Int]

    func total(discount: Int?) -> Int {
        if items.isEmpty { return 0 }
        let sum = items.reduce(0, +)
        return sum - (discount ?? 0)
    }

    func label(count: Int) -> String {
        switch count {
        case 0: return "none"
        case 1: return "one"
        default: return "many"
        }
    }
}

func describe(_ orders: Orders) -> String {
    return orders.label(count: 1)
}
