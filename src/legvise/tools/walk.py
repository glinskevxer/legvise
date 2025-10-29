"""Finding and parsing the package's own source, for the checks to read.

Every check under `legvise.tools` reads the source rather than importing it.
That is deliberate. Importing a module runs it, and a check that runs the code
it is checking cannot be trusted to report on a module that fails to import --
which is exactly the case worth catching.

The AST is parsed once per file and handed to whichever check asked for it.
"""

from __future__ import annotations

import ast
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

__all__ = ["SourceFile", "package_root", "repo_root", "source_files", "suite_files"]


def repo_root() -> Path:
    """The checkout root, found by walking up from this file."""
    return Path(__file__).resolve().parents[3]


def package_root() -> Path:
    """The `legvise` package directory."""
    return Path(__file__).resolve().parents[1]


@dataclass(frozen=True, slots=True)
class SourceFile:
    """One parsed module, with the pieces every check wants."""

    path: Path
    module: str
    tree: ast.Module
    text: str

    @property
    def is_package_init(self) -> bool:
        """True for an `__init__.py`."""
        return self.path.name == "__init__.py"

    @property
    def layer(self) -> str:
        """The subpackage this module belongs to, or the package name itself."""
        parts = self.module.split(".")
        return parts[1] if len(parts) > 2 else parts[0]

    def docstring(self) -> str | None:
        """The module docstring, if it has one."""
        return ast.get_docstring(self.tree)

    def imports(self) -> tuple[str, ...]:
        """Every `legvise` path this module imports, in source order.

        `from legvise.cli import book` names a module, and `from legvise.money
        import dec` names a function, and the AST cannot tell them apart without
        looking at the filesystem. So both the package and the dotted candidate
        are reported, and the caller keeps whichever ones turn out to be real
        modules. Reporting only the package would make every submodule imported
        that way look unreachable.
        """
        found: list[str] = []
        for node in ast.walk(self.tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                if node.module.startswith("legvise"):
                    found.append(node.module)
                    found.extend(f"{node.module}.{alias.name}" for alias in node.names)
            elif isinstance(node, ast.Import):
                found.extend(alias.name for alias in node.names if alias.name.startswith("legvise"))
        return tuple(found)

    def definitions(self) -> Iterator[ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef]:
        """Every function and class defined anywhere in the module."""
        for node in ast.walk(self.tree):
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
                yield node

    def string_constants(self) -> Iterator[str]:
        """Every string literal in the module."""
        for node in ast.walk(self.tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                yield node.value


def _parse(path: Path, root: Path, prefix: str) -> SourceFile:
    text = path.read_text(encoding="utf-8")
    relative = path.relative_to(root).with_suffix("")
    parts = [part for part in relative.parts if part != "__init__"]
    return SourceFile(
        path=path,
        module=".".join([prefix, *parts]) if parts else prefix,
        tree=ast.parse(text, filename=str(path)),
        text=text,
    )


def source_files() -> tuple[SourceFile, ...]:
    """Every module in the package, in path order."""
    root = package_root()
    return tuple(_parse(path, root, "legvise") for path in sorted(root.rglob("*.py")))


def suite_files() -> tuple[SourceFile, ...]:
    """Every test module, in path order.

    Not called `test_files`. Anything importing that name into a test module
    gets it collected as a test case, which fails on the return value rather
    than on anything real, and takes twenty minutes to work out.
    """
    root = repo_root() / "tests"
    return tuple(_parse(path, root, "tests") for path in sorted(root.rglob("*.py")))


def report(name: str, problems: list[str]) -> int:
    """Print a check's findings and return the exit code it should use."""
    if not problems:
        print(f"{name}: clean")
        return 0
    for problem in problems:
        print(f"{name}: {problem}")
    print(f"{name}: {len(problems)} problem(s)")
    return 1
