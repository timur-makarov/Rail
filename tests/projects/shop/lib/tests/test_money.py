from shop_lib.money import total


def test_the_total_is_the_sum() -> None:
    assert total([250, 100]) == 350


def test_an_empty_cart_costs_nothing() -> None:
    assert total([]) == 0
