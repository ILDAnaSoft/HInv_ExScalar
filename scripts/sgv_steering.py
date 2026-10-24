"""Merge options into an SGV steering file (Fortran-namelist-like format).

The steering consists of sections

    &section_name
    ! comment
     KEY = value
       continuation of value
    /

Options are given as {"section.KEY": value}, the same convention as SGVOptions in
hep-workflows, e.g. {"global_steering.MAXEV": 100}. For each option:
  - an active line "KEY = ..." in that section (incl. continuation lines) is replaced,
  - otherwise, if the key appears commented out ("! KEY = ...") in that section, the
    option is added at the end of the section,
  - otherwise a KeyError is raised, unless allow_new=True. This catches typos, which SGV
    would otherwise silently ignore or fail on later.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Union

# Union instead of "|": module-level alias must also evaluate on Python 3.9
Value = Union[str, bool, int, float, Sequence[Union[int, float]]]


def format_value(value: Value) -> str:
    if isinstance(value, str):
        return f"'{value}'"
    if isinstance(value, bool):  # before int: bool is a subclass of int
        return ".TRUE." if value else ".FALSE."
    if isinstance(value, (int, float)):
        return repr(value)
    return " ".join(format_value(v) for v in value)


def _group_by_section(options: Mapping[str, Value]) -> dict[str, dict[str, Value]]:
    grouped: dict[str, dict[str, Value]] = {}
    for name, value in options.items():
        section, sep, key = name.partition(".")
        if not sep or not section or not key:
            raise ValueError(f"Option must be given as 'section.KEY', got '{name}'")
        grouped.setdefault(section, {})[key] = value
    return grouped


def _key_of(line: str, commented: bool) -> str | None:
    pattern = r"^\s*!\s*([A-Za-z_]\w*)\s*=" if commented else r"^\s*([A-Za-z_]\w*)\s*="
    match = re.match(pattern, line)
    return match.group(1) if match else None


def _is_continuation(line: str) -> bool:
    stripped = line.strip()
    return bool(stripped) and stripped[0] not in "!&/" and "=" not in stripped


def merge_options(steering: str, options: Mapping[str, Value], allow_new: bool = False) -> str:
    """Returns the steering text with options merged in (see module docstring)."""
    pending = _group_by_section(options)
    seen_sections = set()
    out: list[str] = []
    section: str | None = None
    commented_keys: set[str] = set()
    skip_continuation = False

    for line in steering.splitlines(keepends=True):
        stripped = line.strip()

        if skip_continuation:
            if _is_continuation(line):
                continue
            skip_continuation = False

        if stripped.startswith("&"):
            section = stripped[1:].split()[0]
            seen_sections.add(section)
            commented_keys = set()
        elif stripped.startswith("/") and section is not None:
            # add options not present as active lines before closing the section
            for key, value in pending.pop(section, {}).items():
                if key not in commented_keys and not allow_new:
                    raise KeyError(f"'{section}.{key}' not found in steering")
                out.append(f" {key} = {format_value(value)}\n")
            section = None
        elif section in pending:
            key = _key_of(line, commented=False)
            if key in pending[section]:
                indent = line[: len(line) - len(line.lstrip())]
                out.append(f"{indent}{key} = {format_value(pending[section].pop(key))}\n")
                skip_continuation = True
                continue
            commented = _key_of(line, commented=True)
            if commented:
                commented_keys.add(commented)

        out.append(line)

    unknown = set(pending) - seen_sections
    if unknown:
        raise KeyError(f"Sections not found in steering: {sorted(unknown)}")
    return "".join(out)
