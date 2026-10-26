from shop import shipping


def test_fifty_ships_free():
    assert shipping(50) == 0
    assert shipping(60) == 0


def test_under_fifty_costs_five():
    assert shipping(49) == 5
