module Demo.Orders

let total (items: int list) (discount: int option) =
    if List.isEmpty items then 0
    else List.sum items - defaultArg discount 0

let label count =
    match count with
    | 0 -> "none"
    | 1 -> "one"
    | _ -> "many"

let describe items = label (List.length items)
