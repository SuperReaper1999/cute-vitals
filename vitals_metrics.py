"""Pure Linux system metric parsers; no GPU or Qt dependencies."""

from typing import Optional


def parse_meminfo(text: str) -> Optional[tuple[float, float]]:
    """Return (used MiB, total MiB) from Linux /proc/meminfo, or None."""
    values: dict[str, float] = {}
    for line in text.splitlines():
        key, sep, rest = line.partition(":")
        if not sep or key not in ("MemTotal", "MemAvailable"):
            continue
        fields = rest.split()
        if len(fields) < 2 or fields[1] != "kB":
            continue
        try:
            value = int(fields[0])
        except ValueError:
            continue
        if value >= 0:
            values[key] = value / 1024

    total = values.get("MemTotal")
    available = values.get("MemAvailable")
    if total is None or total <= 0 or available is None or available > total:
        return None
    return total - available, total


def parse_cpu_stats(text: str) -> list[tuple[str, int, int]]:
    """Return (CPU name, cumulative ticks, idle ticks) for valid /proc/stat rows."""
    rows: list[tuple[str, int, int]] = []
    for line in text.splitlines():
        fields = line.split()
        if not fields:
            continue
        name = fields[0]
        if name != "cpu" and not (name.startswith("cpu") and name[3:].isdigit()):
            continue
        try:
            counts = [int(value) for value in fields[1:]]
        except ValueError:
            continue
        if len(counts) < 4 or any(value < 0 for value in counts):
            continue
        idle = counts[3] + (counts[4] if len(counts) > 4 else 0)
        rows.append((name, sum(counts), idle))
    return rows
