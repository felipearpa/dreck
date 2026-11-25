package demo

class Orders(private val items: List<Int>) {
    fun total(discount: Int?): Int {
        if (items.isEmpty()) return 0
        val sum = items.sum()
        return sum - (discount ?: 0)
    }

    fun label(count: Int): String = when (count) {
        0 -> "none"
        1 -> "one"
        else -> "many"
    }
}

fun describe(orders: Orders): String {
    return orders.label(1)
}
