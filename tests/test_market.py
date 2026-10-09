from market import buy_thresholds, percentile


def test_percentile_picks_the_nearest_rank():
    prices = [500, 400, 300, 200, 100]
    assert percentile(prices, 0) == 100
    assert percentile(prices, 50) == 300
    assert percentile(prices, 100) == 500


def test_fixed_price_only():
    assert buy_thresholds(650) == (650, None)
    assert buy_thresholds(650, None, 400) == (650, 400)


def test_history_raises_the_buy_threshold_but_not_the_exceptional_one():
    # A week of expensive fuel: buy at the percentile, exceptional only below the fixed good price.
    assert buy_thresholds(650, 900, 850) == (900, 650)


def test_cheap_history_keeps_the_fixed_price_as_buy_threshold():
    assert buy_thresholds(650, 500, 480) == (650, 480)


def test_equal_percentiles_never_make_every_purchase_exceptional():
    # buy_percentile == excellent_percentile used to give buy_at == excellent_at.
    buy_at, excellent_at = buy_thresholds(650, 700, 700)
    assert buy_at == 700
    assert excellent_at == 650
    buy_at, excellent_at = buy_thresholds(650, 650, 650)
    assert (buy_at, excellent_at) == (650, None)


def test_exceptional_is_always_strictly_below_the_buy_threshold():
    for fixed in (0, 100, 650, 1000):
        for history in (None, 50, 650, 900):
            for top in (None, 40, 650, 900):
                buy_at, excellent_at = buy_thresholds(fixed, history, top)
                assert excellent_at is None or excellent_at < buy_at
                assert excellent_at is None or fixed <= 0 or excellent_at <= fixed


def test_without_fixed_price_the_history_alone_decides():
    assert buy_thresholds(0, 900, 800) == (900, 800)
