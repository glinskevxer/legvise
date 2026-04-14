"""Where the inventory is against where it wants to be."""

from __future__ import annotations

from legvise.model.inventory import Band, Position
from legvise.money import dec
from legvise.report.inventory_report import build_inventory_report

AS_OF = "2026-04-16T09:00:00+00:00"


def holding(venue: str, asset: str, free: str) -> Position:
    return Position.build(venue, asset, free=free, as_of=AS_OF)


def band(venue: str, asset: str, target: str, floor: str = "0", ceiling: str = "1000") -> Band:
    return Band.build(venue, asset, floor=floor, target=target, ceiling=ceiling)


def bands(*given: Band) -> dict[tuple[str, str], Band]:
    return {(item.venue, item.asset): item for item in given}


def test_a_desk_on_target_everywhere_is_square() -> None:
    found = build_inventory_report(
        (holding("kraken", "BTC", "5"),),
        bands(band("kraken", "BTC", "5")),
    )
    plan = found.plan_for("BTC")
    assert plan is not None
    assert plan.is_square


def test_a_venue_long_of_its_target_has_a_positive_gap() -> None:
    found = build_inventory_report(
        (holding("kraken", "BTC", "8"),),
        bands(band("kraken", "BTC", "5")),
    )
    assert found.plans[0].gaps[0].gap == dec("3")
    assert found.plans[0].surplus == dec("3")


def test_a_venue_short_of_its_target_has_a_negative_gap() -> None:
    found = build_inventory_report(
        (holding("kraken", "BTC", "2"),),
        bands(band("kraken", "BTC", "5")),
    )
    assert found.plans[0].gaps[0].gap == dec("-3")
    assert found.plans[0].deficit == dec("3")


def test_a_surplus_and_a_deficit_cancel_into_a_transfer() -> None:
    found = build_inventory_report(
        (holding("kraken", "BTC", "8"), holding("okx", "BTC", "2")),
        bands(band("kraken", "BTC", "5"), band("okx", "BTC", "5")),
    )
    plan = found.plans[0]
    assert plan.transferable == dec("3")
    assert plan.net_move == dec("0")


def test_a_desk_long_overall_has_something_to_sell() -> None:
    found = build_inventory_report(
        (holding("kraken", "BTC", "9"), holding("okx", "BTC", "4")),
        bands(band("kraken", "BTC", "5"), band("okx", "BTC", "5")),
    )
    plan = found.plans[0]
    assert plan.net_move == dec("3")
    assert plan.transferable == dec("1")


def test_a_desk_short_overall_has_something_to_buy() -> None:
    found = build_inventory_report(
        (holding("kraken", "BTC", "3"), holding("okx", "BTC", "4")),
        bands(band("kraken", "BTC", "5"), band("okx", "BTC", "5")),
    )
    assert found.plans[0].net_move == dec("-3")


def test_a_holding_with_no_band_targets_itself_and_reads_as_unbanded() -> None:
    found = build_inventory_report((holding("kraken", "SOL", "100"),), {})
    gap = found.plans[0].gaps[0]
    assert gap.gap == dec("0")
    assert gap.state == "no band"


def test_a_holding_under_its_floor_is_reported_as_out_of_band() -> None:
    found = build_inventory_report(
        (holding("kraken", "BTC", "0.5"),),
        bands(band("kraken", "BTC", "5", floor="1")),
    )
    assert found.out_of_band[0].state == "under floor"


def test_a_holding_over_its_ceiling_is_reported_as_out_of_band() -> None:
    found = build_inventory_report(
        (holding("kraken", "BTC", "50"),),
        bands(band("kraken", "BTC", "5", ceiling="9")),
    )
    assert found.out_of_band[0].state == "over ceiling"


def test_a_holding_inside_its_band_is_not_reported() -> None:
    found = build_inventory_report(
        (holding("kraken", "BTC", "5"),),
        bands(band("kraken", "BTC", "5")),
    )
    assert found.out_of_band == ()


def test_only_the_assets_a_transfer_would_help_are_listed() -> None:
    found = build_inventory_report(
        (
            holding("kraken", "BTC", "8"),
            holding("okx", "BTC", "2"),
            holding("kraken", "USD", "5"),
        ),
        bands(band("kraken", "BTC", "5"), band("okx", "BTC", "5"), band("kraken", "USD", "5")),
    )
    assert [plan.asset for plan in found.needs_transfers] == ["BTC"]


def test_the_assets_come_back_in_order() -> None:
    found = build_inventory_report(
        (holding("kraken", "USD", "5"), holding("kraken", "BTC", "5")),
        bands(band("kraken", "USD", "5"), band("kraken", "BTC", "5")),
    )
    assert [plan.asset for plan in found.plans] == ["BTC", "USD"]


def test_an_asset_the_desk_does_not_hold_has_no_plan() -> None:
    found = build_inventory_report((), {})
    assert found.plan_for("BTC") is None


def test_a_gap_of_nothing_does_not_need_moving() -> None:
    found = build_inventory_report(
        (holding("kraken", "BTC", "5"),),
        bands(band("kraken", "BTC", "5")),
    )
    assert not found.plans[0].gaps[0].needs_moving
