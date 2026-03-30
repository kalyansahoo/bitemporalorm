from __future__ import annotations

import importlib.util
import os
import re
from dataclasses import dataclass, field

from bitemporalorm.migration.ops import Operation


@dataclass
class LoadedMigration:
    name: str               # e.g. "0001_initial"
    filepath: str
    dependencies: list[str]
    operations: list[Operation]


class MigrationLoader:
    """Discovers and topologically sorts migration files."""

    def __init__(self, migrations_dir: str) -> None:
        self.migrations_dir = migrations_dir

    def load(self) -> list[LoadedMigration]:
        """Load all migration files, topologically sorted."""
        if not os.path.isdir(self.migrations_dir):
            return []

        raw: list[LoadedMigration] = []
        for fname in sorted(os.listdir(self.migrations_dir)):
            if not re.match(r"^\d{4}_.*\.py$", fname):
                continue
            name     = fname[:-3]  # strip .py
            filepath = os.path.join(self.migrations_dir, fname)
            mig      = self._load_file(name, filepath)
            raw.append(mig)

        return _topological_sort(raw)

    def _load_file(self, name: str, filepath: str) -> LoadedMigration:
        spec   = importlib.util.spec_from_file_location(name, filepath)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        dependencies: list[str] = getattr(module, "dependencies", [])
        operations: list[Operation] = getattr(module, "operations", [])

        return LoadedMigration(
            name=name,
            filepath=filepath,
            dependencies=dependencies,
            operations=operations,
        )


def _topological_sort(migrations: list[LoadedMigration]) -> list[LoadedMigration]:
    """Kahn's algorithm topological sort on migration dependencies."""
    by_name = {m.name: m for m in migrations}

    # Build in-degree map
    in_degree: dict[str, int] = {m.name: 0 for m in migrations}
    dependents: dict[str, list[str]] = {m.name: [] for m in migrations}

    for mig in migrations:
        for dep in mig.dependencies:
            if dep not in by_name:
                raise ValueError(
                    f"Migration '{mig.name}' depends on '{dep}' which was not found."
                )
            in_degree[mig.name] += 1
            dependents[dep].append(mig.name)

    queue = [name for name, deg in in_degree.items() if deg == 0]
    result: list[LoadedMigration] = []

    while queue:
        name = queue.pop(0)
        result.append(by_name[name])
        for dep_name in dependents[name]:
            in_degree[dep_name] -= 1
            if in_degree[dep_name] == 0:
                queue.append(dep_name)

    if len(result) != len(migrations):
        cycle = [m.name for m in migrations if m.name not in {r.name for r in result}]
        raise ValueError(f"Circular dependency detected in migrations: {cycle}")

    return result
