"""Three levels of settings, and which one decided each number."""

from __future__ import annotations

from pathlib import Path

import pytest

from legvise.errors import BadArgument, NotFound
from legvise.settings import DEFAULTS, SECTION, Resolved, Settings, load, resolve, settled


def a_file(tmp_path: Path, body: str, name: str = "legvise.toml") -> Path:
    """A settings file on disk, written the way an operator would write it."""
    path = tmp_path / name
    path.write_text(body, encoding="utf-8")
    return path


def source_of(name: str, **kwargs: object) -> str:
    """The level that decided one setting."""
    found = resolve(**kwargs)  # type: ignore[arg-type]
    return next(item.source for item in found if item.name == name)


def value_of(name: str, **kwargs: object) -> str | int:
    """The value one setting resolved to."""
    found = resolve(**kwargs)  # type: ignore[arg-type]
    return next(item.value for item in found if item.name == name)


def test_the_shipped_settings_cover_the_scan_options() -> None:
    assert "min_edge_bps" in DEFAULTS.names()
    assert "stranded_bps" in DEFAULTS.names()
    assert len(DEFAULTS.names()) == 9


def test_a_setting_can_be_read_by_name() -> None:
    assert DEFAULTS.value_of("min_edge_bps") == "2"
    assert DEFAULTS.value_of("window_ms") == 250


def test_a_name_that_is_not_a_setting_is_refused() -> None:
    with pytest.raises(BadArgument) as caught:
        DEFAULTS.value_of("min_edge_bp")
    assert "is not one of the desk" in caught.value.why


def test_nothing_set_anywhere_reads_as_the_shipped_value() -> None:
    assert value_of("min_edge_bps") == "2"
    assert source_of("min_edge_bps") == "default"


def test_every_setting_resolves_to_something() -> None:
    assert len(resolve()) == len(DEFAULTS.names())


def test_the_file_beats_what_the_tool_ships_with() -> None:
    assert value_of("min_edge_bps", from_file={"min_edge_bps": "9"}) == "9"
    assert source_of("min_edge_bps", from_file={"min_edge_bps": "9"}) == "file"


def test_a_flag_beats_the_file() -> None:
    both = {"from_file": {"min_edge_bps": "9"}, "from_flags": {"min_edge_bps": "11"}}
    assert value_of("min_edge_bps", **both) == "11"
    assert source_of("min_edge_bps", **both) == "flag"


def test_a_flag_that_was_not_given_does_not_beat_the_file() -> None:
    both = {"from_file": {"min_edge_bps": "9"}, "from_flags": {"min_edge_bps": None}}
    assert value_of("min_edge_bps", **both) == "9"
    assert source_of("min_edge_bps", **both) == "file"


def test_a_flag_beats_the_default_with_no_file_at_all() -> None:
    assert source_of("size", from_flags={"size": "4"}) == "flag"


def test_setting_one_number_leaves_the_others_alone() -> None:
    found = resolve(from_file={"min_edge_bps": "9"})
    assert [item.source for item in found].count("file") == 1
    assert [item.source for item in found].count("default") == len(DEFAULTS.names()) - 1


def test_a_default_says_it_is_one() -> None:
    assert Resolved(name="size", value="1", source="default").is_default


def test_a_value_from_the_file_is_not_a_default() -> None:
    assert not Resolved(name="size", value="4", source="file").is_default


def test_the_resolved_numbers_collapse_into_one_record() -> None:
    found = settled(resolve(from_file={"min_edge_bps": "9", "cycles": 4}))
    assert found == Settings(min_edge_bps="9", cycles=4)


def test_a_file_that_sets_nothing_reads_as_nothing(tmp_path: Path) -> None:
    assert load(a_file(tmp_path, "")) == {}


def test_a_file_with_only_other_tables_reads_as_nothing(tmp_path: Path) -> None:
    assert load(a_file(tmp_path, '[export]\nformat = "csv"\n')) == {}


def test_a_file_sets_what_it_names(tmp_path: Path) -> None:
    found = load(a_file(tmp_path, f'[{SECTION}]\nmin_edge_bps = "9"\nwindow_ms = 400\n'))
    assert found == {"min_edge_bps": "9", "window_ms": 400}


def test_a_number_written_as_a_number_is_kept_as_its_text(tmp_path: Path) -> None:
    found = load(a_file(tmp_path, f"[{SECTION}]\nmin_edge_bps = 9\n"))
    assert found == {"min_edge_bps": "9"}


def test_a_decimal_in_the_file_keeps_its_places(tmp_path: Path) -> None:
    found = load(a_file(tmp_path, f"[{SECTION}]\nmin_edge_bps = 2.5\n"))
    assert found == {"min_edge_bps": "2.5"}


def test_a_key_nobody_recognises_is_refused(tmp_path: Path) -> None:
    with pytest.raises(BadArgument) as caught:
        load(a_file(tmp_path, f'[{SECTION}]\nmin_edge_bp = "9"\n'))
    assert "is not a setting" in caught.value.why


def test_a_whole_number_setting_refuses_text(tmp_path: Path) -> None:
    with pytest.raises(BadArgument) as caught:
        load(a_file(tmp_path, f'[{SECTION}]\nwindow_ms = "400"\n'))
    assert "takes a whole number" in caught.value.why


def test_a_whole_number_setting_refuses_a_flag(tmp_path: Path) -> None:
    with pytest.raises(BadArgument):
        load(a_file(tmp_path, f"[{SECTION}]\nwindow_ms = true\n"))


def test_a_number_setting_refuses_a_flag(tmp_path: Path) -> None:
    with pytest.raises(BadArgument) as caught:
        load(a_file(tmp_path, f"[{SECTION}]\nmin_edge_bps = true\n"))
    assert "takes a number or its text" in caught.value.why


def test_a_number_setting_refuses_a_list(tmp_path: Path) -> None:
    with pytest.raises(BadArgument):
        load(a_file(tmp_path, f"[{SECTION}]\nmin_edge_bps = [1, 2]\n"))


def test_a_scan_section_that_is_not_a_table_is_refused(tmp_path: Path) -> None:
    with pytest.raises(BadArgument) as caught:
        load(a_file(tmp_path, f'{SECTION} = "everything"\n'))
    assert "has to be a table" in caught.value.why


def test_a_file_that_is_not_toml_is_refused(tmp_path: Path) -> None:
    with pytest.raises(BadArgument) as caught:
        load(a_file(tmp_path, "this is not = = toml\n"))
    assert "not readable TOML" in caught.value.why


def test_a_file_that_is_not_there_is_a_not_found(tmp_path: Path) -> None:
    with pytest.raises(NotFound):
        load(tmp_path / "nowhere.toml")


def test_a_loaded_file_feeds_straight_into_the_resolver(tmp_path: Path) -> None:
    from_file = load(a_file(tmp_path, f"[{SECTION}]\ncycles = 4\n"))
    assert value_of("cycles", from_file=from_file) == 4
    assert source_of("cycles", from_file=from_file) == "file"


# The example file that ships with the tree. The README shows a `[scan]` table
# and CI runs `config check` against this one, so it has to stay loadable and
# it has to keep naming settings that exist.


def example_file() -> Path:
    """The settings file the repository ships as documentation."""
    return Path(__file__).resolve().parents[1] / "examples" / "legvise.toml"


def test_the_example_settings_file_is_there() -> None:
    assert example_file().exists()


def test_the_example_settings_file_loads() -> None:
    assert load(example_file())


def test_the_example_names_every_setting_the_desk_has() -> None:
    assert set(load(example_file())) == set(DEFAULTS.names())


def test_the_example_sets_them_all_from_the_file() -> None:
    found = resolve(from_file=load(example_file()))
    assert all(item.source == "file" for item in found)


def test_the_example_settings_collapse_into_a_record() -> None:
    found = settled(resolve(from_file=load(example_file())))
    assert found.min_edge_bps == "4"
    assert found.window_ms == 400


def test_the_example_explains_what_each_number_does() -> None:
    text = example_file().read_text(encoding="utf-8")
    assert text.count("#") > 15
