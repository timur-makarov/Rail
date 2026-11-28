"""What a cart costs."""

from shop_lib.money import total


def bill(prices: list[int], shipping: int = 0) -> int:
    """The cart's total in cents, with shipping."""
    return total(prices) + shipping
