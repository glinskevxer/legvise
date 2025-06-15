"""Transfer networks, and whether a venue will use one."""

from __future__ import annotations

import pytest

from legvise.errors import BadArgument
from legvise.model.network import TransferNetwork, VenueNetwork, network_code
from legvise.money import dec


def a_network(**changes: object) -> TransferNetwork:
    fields: dict[str, object] = {
        "asset": "USDT",
        "code": "TRX",
        "withdraw_fee": "1",
        "min_withdraw": "10",
        "confirmations": 20,
        "minutes_per_confirmation": "0.05",
    }
    fields.update(changes)
    return TransferNetwork.build(**fields)  # type: ignore[arg-type]


def test_a_network_code_comes_back_upper_case() -> None:
    assert network_code(" trx ") == "TRX"
    assert network_code("arbitrum-one") == "ARBITRUM-ONE"


@pytest.mark.parametrize("bad", ["", "T", "ether net", "_ETH"])
def test_a_network_code_that_breaks_the_shape_is_refused(bad: str) -> None:
    with pytest.raises(BadArgument):
        network_code(bad)


def test_a_network_keys_on_the_asset_and_the_code() -> None:
    assert a_network().key == ("USDT", "TRX")


def test_settlement_time_is_confirmations_times_block_time() -> None:
    assert a_network().settle_minutes == dec("1.00")
    assert a_network(confirmations=12, minutes_per_confirmation="0.2").settle_minutes == dec("2.4")


def test_the_amount_arriving_is_net_of_the_withdrawal_fee() -> None:
    assert a_network().net_of_fee(dec("100")) == dec("99")


def test_an_amount_below_the_network_minimum_is_refused() -> None:
    with pytest.raises(BadArgument) as caught:
        a_network().net_of_fee(dec("5"))
    assert "TRX minimum" in caught.value.why


def test_an_amount_exactly_on_the_minimum_is_allowed() -> None:
    assert a_network().net_of_fee(dec("10")) == dec("9")


def test_a_free_network_is_allowed() -> None:
    assert a_network(withdraw_fee="0").net_of_fee(dec("100")) == dec("100")


def test_a_negative_withdrawal_fee_is_refused() -> None:
    with pytest.raises(BadArgument) as caught:
        a_network(withdraw_fee="-1")
    assert caught.value.field == "withdraw_fee"


def test_a_minimum_withdrawal_of_zero_is_refused() -> None:
    with pytest.raises(BadArgument):
        a_network(min_withdraw="0")


@pytest.mark.parametrize("count", [0, -1])
def test_a_transfer_needs_at_least_one_confirmation(count: int) -> None:
    with pytest.raises(BadArgument) as caught:
        a_network(confirmations=count)
    assert caught.value.field == "confirmations"


def test_a_block_time_of_zero_is_refused() -> None:
    with pytest.raises(BadArgument):
        a_network(minutes_per_confirmation="0")


def test_a_venue_network_keys_on_all_three() -> None:
    entry = VenueNetwork.build("kraken", "usdt", "trx")
    assert entry.key == ("kraken", "USDT", "TRX")


def test_a_venue_network_is_open_both_ways_unless_told_otherwise() -> None:
    entry = VenueNetwork.build("kraken", "USDT", "TRX")
    assert entry.deposit_enabled
    assert entry.withdraw_enabled


def test_a_suspended_withdrawal_is_recorded_as_such() -> None:
    entry = VenueNetwork.build("kraken", "USDT", "TRX", withdraw_enabled=False)
    assert entry.deposit_enabled
    assert not entry.withdraw_enabled


def test_an_unnormalised_code_cannot_be_constructed_directly() -> None:
    with pytest.raises(BadArgument):
        VenueNetwork(
            venue="kraken",
            asset="USDT",
            network="trx",
            deposit_enabled=True,
            withdraw_enabled=True,
        )
