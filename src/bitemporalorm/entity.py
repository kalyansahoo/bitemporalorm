from __future__ import annotations

import sys
from datetime import datetime
from typing import Any, cast

import polars as pl

from bitemporalorm.fields import (
    FieldSpec,
    _BitemporalField,
    to_snake_case,
)
from bitemporalorm.registry import registry

# ---------------------------------------------------------------------------
# EntityOptions
# ---------------------------------------------------------------------------


class EntityOptions:
    def __init__(
        self,
        table_name: str,
        fields: dict[str, FieldSpec],
        parent_entity: type[Entity] | None,
    ) -> None:
        self.table_name = table_name
        self.fields = fields  # own fields only
        self.parent_entity = parent_entity  # direct parent Entity class (or None)

    def all_fields(self) -> dict[str, FieldSpec]:
        """Returns own fields + all inherited fields (flattened)."""
        if self.parent_entity is None:
            return dict(self.fields)
        parent_fields = self.parent_entity._meta.all_fields()
        return {**parent_fields, **self.fields}

    def hierarchy(self) -> list[type[Entity]]:
        """Returns [self_class, parent, grandparent, ...] walking up the chain."""
        chain: list[type[Entity]] = []
        parent = self.parent_entity
        while parent is not None:
            chain.append(parent)
            parent = parent._meta.parent_entity
        return chain


# ---------------------------------------------------------------------------
# EntityMeta
# ---------------------------------------------------------------------------


class EntityMeta(type):
    def __new__(
        mcs,
        name: str,
        bases: tuple[type, ...],
        namespace: dict[str, Any],
        **kwargs: Any,
    ) -> type:
        cls = super().__new__(mcs, name, bases, namespace, **kwargs)

        # Skip the Entity base class itself
        if name == "Entity" and not any(isinstance(b, EntityMeta) for b in bases):
            return cls

        # ---- Resolve annotations ----------------------------------------
        # Use raw __annotations__ from vars(cls) — reliable for both module-level
        # and function-local classes.  get_type_hints is unreliable in Python 3.14
        # for dynamically-created or locally-scoped classes.
        mod_ns = getattr(sys.modules.get(cls.__module__, None), "__dict__", {})
        # Python 3.14 (PEP 749) stores annotations in __annotate__ rather than
        # directly in __dict__; cls.__annotations__ triggers the descriptor and
        # always returns the evaluated dict, whereas vars(cls).get(...) returns {}.
        try:
            own_annotations: dict = cls.__annotations__
        except AttributeError:
            own_annotations = {}

        # ---- Detect parent Entity ----------------------------------------
        entity_parents = [b for b in bases if isinstance(b, EntityMeta) and b.__name__ != "Entity"]
        if len(entity_parents) > 1:
            raise TypeError(
                f"Entity '{name}' has multiple entity parents "
                f"({[p.__name__ for p in entity_parents]}). Multiple inheritance is not allowed."
            )
        parent_entity: type[Entity] | None = (
            cast("type[Entity]", entity_parents[0]) if entity_parents else None
        )

        # ---- Collect own field annotations --------------------------------
        fields: dict[str, FieldSpec] = {}

        for attr_name, ann in own_annotations.items():
            if attr_name.startswith("_"):
                continue

            # Resolve string annotations (from __future__ annotations or forward refs)
            if isinstance(ann, str):
                try:
                    ann = eval(ann, mod_ns)
                except Exception:
                    continue

            # Check if it is a _BitemporalField instance (ManyToOneField[str] syntax)
            # or a _BitemporalField subclass (bare ManyToOneField usage).
            field_inst: _BitemporalField | None = None

            if isinstance(ann, _BitemporalField):
                field_inst = ann
            elif isinstance(ann, type) and issubclass(ann, _BitemporalField):
                field_inst = ann()
            else:
                continue  # not a bitemporal field

            field_inst.name = attr_name
            field_inst.owner = cls

            sql_type, entity_ref = field_inst._resolve_field_type(registry)

            fields[attr_name] = FieldSpec(
                name=attr_name,
                relationship=field_inst.relationship,
                sql_type=sql_type,
                entity_ref=entity_ref,
            )

        # ---- Build Meta inner class override --------------------------------
        inner_meta = vars(cls).get("Meta", None)
        table_name = getattr(inner_meta, "table_name", None) or to_snake_case(name)

        # ---- Attach _meta --------------------------------------------------
        cls._meta = EntityOptions(  # type: ignore[attr-defined]
            table_name=table_name,
            fields=fields,
            parent_entity=parent_entity,
        )

        # Register
        registry.register(cls)  # type: ignore[arg-type]
        return cls


# ---------------------------------------------------------------------------
# Entity base class
# ---------------------------------------------------------------------------


class Entity(metaclass=EntityMeta):
    """Base class for all bitemporal entities."""

    _meta: EntityOptions  # set by EntityMeta

    # -----------------------------------------------------------------------
    # save()
    # -----------------------------------------------------------------------

    @classmethod
    async def save(cls, df: pl.DataFrame) -> pl.DataFrame:
        """
        Persist a DataFrame of entity events.

        Required columns: as_of_start
        Optional columns: as_of_end (default infinity), entity_id, <field_name>...

        Returns the DataFrame with entity_id populated for all rows.
        """
        from bitemporalorm.query.executor import get_executor

        executor = get_executor()
        return await executor.save_entity(cls, df)

    # -----------------------------------------------------------------------
    # filter()
    # -----------------------------------------------------------------------

    @classmethod
    async def filter(cls, as_of: datetime, *exprs: Any) -> pl.DataFrame:
        """
        Query entities as of a specific point in time.

        Parameters
        ----------
        as_of:
            Point-in-time datetime. Translated to ``field_table.as_of @> as_of``.
        *exprs:
            Optional Polars expressions for additional WHERE conditions.
            e.g. ``pl.col("city") == "London"``

        Returns
        -------
        pl.DataFrame
            One row per (entity, one-to-many value) combination.
        """
        from bitemporalorm.query.builder import build_filter_sql
        from bitemporalorm.query.executor import get_executor

        executor = get_executor()
        sql, params = build_filter_sql(cls, as_of, list(exprs))
        return await executor.read_as_dataframe(sql, params)
