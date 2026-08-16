"""The desk's standing numbers, and where each one came from.

`scan run` takes eleven options. A desk runs it every few seconds from a
scheduler, and eleven options typed into a crontab is a configuration file
written badly: nobody can see it, nobody reviews it, and the number that got
changed at three in the morning is in a shell history on one machine.

So the numbers live in a file, and the flags still win. Three levels, and the
order is the only part of this worth thinking about:

1. what the tool ships with
2. what the file says
3. what the operator typed

A flag beating the file is what makes the file safe to keep. An operator trying
a wider edge floor for one run should not have to edit the desk's settings and
remember to put them back, and the run that follows should not inherit it.

The part that costs an afternoon is not the precedence. It is not knowing which
level a number came from, so `resolve` returns the source alongside the value
and `legvise config show` prints both. A setting that reads 2 because the file
says 2 and a setting that reads 2 because nobody ever set it are different
situations, and they look identical in a number.

Unknown keys are refused rather than ignored. A file with `min_edge_bp` in it
is a file where somebody set the edge floor and the desk has been trading on
the default ever since, and ignoring the typo is what let that happen.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Any, Final

from legvise.errors import BadArgument, NotFound

__all__ = ["DEFAULTS", "Resolved", "Settings", "load", "resolve", "settled"]

SECTION: Final = "scan"


@dataclass(frozen=True, slots=True)
class Settings:
    """Every number a scan takes, with the values the tool ships with."""

    min_edge_bps: str = "2"
    window_ms: int = 250
    size: str = "1"
    venue_cap: str = "250000"
    asset_cap: str = "400000"
    gross_cap: str = "1000000"
    carry_bps_hour: str = "6"
    cycles: int = 10
    stranded_bps: str = "250"

    @classmethod
    def names(cls) -> tuple[str, ...]:
        """Every setting, in the order they are declared."""
        return tuple(field.name for field in fields(cls))

    def value_of(self, name: str) -> str | int:
        """One setting by name, refusing a name that is not one."""
        if name not in self.names():
            raise BadArgument("setting", name, "is not one of the desk's settings")
        return getattr(self, name)  # type: ignore[no-any-return]


DEFAULTS: Final = Settings()


@dataclass(frozen=True, slots=True)
class Resolved:
    """One setting, its value, and which of the three levels it came from."""

    name: str
    value: str | int
    source: str

    @property
    def is_default(self) -> bool:
        """True when nobody has set this and it is running on the shipped value."""
        return self.source == "default"


def _typed(name: str, given: object, shipped: str | int) -> str | int:
    """One value from the file, checked against the type the setting takes."""
    if isinstance(shipped, int) and not isinstance(shipped, bool):
        if isinstance(given, bool) or not isinstance(given, int):
            raise BadArgument(name, str(given), "this setting takes a whole number")
        return given
    if isinstance(given, bool) or not isinstance(given, str | int | float):
        raise BadArgument(name, str(given), "this setting takes a number or its text")
    return str(given)


def load(path: Path) -> dict[str, str | int]:
    """Read the settings out of a TOML file, refusing anything unexpected.

    Only the `[scan]` table is read. A file may hold other tables -- a desk
    keeps one file, and the scanner is not the only thing reading it -- so an
    unknown table is not an error and an unknown key inside `[scan]` is.
    """
    if not path.exists():
        raise NotFound("config file", str(path))
    try:
        document = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise BadArgument("config", str(path), f"is not readable TOML: {exc}") from exc
    section = document.get(SECTION, {})
    if not isinstance(section, dict):
        raise BadArgument("config", SECTION, "has to be a table")
    return _read_section(section)


def _read_section(section: dict[str, Any]) -> dict[str, str | int]:
    known = DEFAULTS.names()
    found: dict[str, str | int] = {}
    for key, given in section.items():
        if key not in known:
            raise BadArgument(key, str(given), f"is not a setting; the ones there are: {known}")
        found[key] = _typed(key, given, getattr(DEFAULTS, key))
    return found


def resolve(
    from_file: dict[str, str | int] | None = None,
    from_flags: dict[str, str | int | None] | None = None,
) -> tuple[Resolved, ...]:
    """Every setting with its value and the level that decided it."""
    file_values = from_file or {}
    flag_values = {name: value for name, value in (from_flags or {}).items() if value is not None}
    found: list[Resolved] = []
    for name in DEFAULTS.names():
        if name in flag_values:
            found.append(Resolved(name=name, value=flag_values[name], source="flag"))
        elif name in file_values:
            found.append(Resolved(name=name, value=file_values[name], source="file"))
        else:
            found.append(Resolved(name=name, value=getattr(DEFAULTS, name), source="default"))
    return tuple(found)


def settled(resolved: tuple[Resolved, ...]) -> Settings:
    """The resolved settings as one record, for a caller that wants the numbers."""
    return Settings(**{item.name: item.value for item in resolved})  # type: ignore[arg-type]
