class ShopError(Exception):
    pass


class EmptyCart(ShopError):
    pass


class InvalidQuantity(ShopError):
    pass


class OutOfStock(ShopError):
    pass


class PaymentDeclined(ShopError):
    pass
