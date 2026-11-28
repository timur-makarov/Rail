from shop_api.bill import bill


def test_a_cart_costs_its_prices_and_shipping() -> None:
    assert bill([250, 100], shipping=50) == 400
