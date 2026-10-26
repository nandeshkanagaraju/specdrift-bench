from shop.errors import OutOfStock


class Inventory:
    def __init__(self, stock: dict[str, int]) -> None:
        self.stock = dict(stock)

    def reserve(self, items: dict[str, int]) -> None:
        for sku, qty in items.items():
            if self.stock.get(sku, 0) < qty:
                raise OutOfStock(sku)
        for sku, qty in items.items():
            self.stock[sku] -= qty

    def release(self, items: dict[str, int]) -> None:
        for sku, qty in items.items():
            self.stock[sku] += qty
