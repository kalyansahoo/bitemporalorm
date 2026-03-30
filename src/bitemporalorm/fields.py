from __future__ import annotations

import re
from enum import Enum
from typing import Any, Generic, TypeVar

T = TypeVar("T")

# ---------------------------------------------------------------------------
# FieldType
# ---------------------------------------------------------------------------


class FieldType(str, Enum):
    TEXT = "TEXT"
    INT = "BIGINT"
    FLOAT = "DOUBLE PRECISION"
    DATETIME = "TIMESTAMPTZ"
    ENTITY_REF = "BIGINT"  # FK to another entity table; same SQL type as INT


# Python type → FieldType (primitives only)
_PY_TYPE_MAP: dict[type, FieldType] = {
    str: FieldType.TEXT,
    int: FieldType.INT,
    float: FieldType.FLOAT,
}

# String annotation names for primitive types
_STR_TYPE_MAP: dict[str, FieldType] = {
    "str": FieldType.TEXT,
    "int": FieldType.INT,
    "float": FieldType.FLOAT,
    "datetime": FieldType.DATETIME,
}


# ---------------------------------------------------------------------------
# Relationship types
# ---------------------------------------------------------------------------


class RelationshipType(str, Enum):
    MANY_TO_ONE = "many_to_one"  # many entities share the same value (e.g. city)
    ONE_TO_ONE = "one_to_one"  # one value per entity at any time
    ONE_TO_MANY = "one_to_many"  # multiple values per entity → exploded rows


# ---------------------------------------------------------------------------
# Field descriptors
# ---------------------------------------------------------------------------


class _BitemporalField(Generic[T]):
    """Base class for all bitemporal field descriptors."""

    relationship: RelationshipType

    def __init_subclass__(cls, relationship: RelationshipType, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        cls.relationship = relationship

    def __class_getitem__(cls, item: Any) -> _BitemporalField:
        """Support ManyToOneField[str] syntax → returns a parameterised instance."""
        inst = cls.__new__(cls)
        inst._type_arg = item
        return inst

    def __init__(self, _type_arg: Any = None) -> None:
        self._type_arg = _type_arg

    # ------------------------------------------------------------------
    # Resolved at class-creation time by EntityMeta
    # ------------------------------------------------------------------
    name: str = ""  # column / attribute name (set by EntityMeta)
    owner: type | None = None  # owning Entity class

    def _resolve_field_type(self, registry_getter: Any) -> tuple[FieldType, str | None]:
        """
        Returns (FieldType, entity_ref_name).
        entity_ref_name is not None when the value type is a forward-ref to another Entity.
        """
        arg = self._type_arg
        if arg is None:
            raise ValueError(f"Field '{self.name}' has no type argument")

        # String forward reference  e.g. "BusinessEntity"
        if isinstance(arg, str):
            # Check if it's a primitive type name
            if arg in _STR_TYPE_MAP:
                return _STR_TYPE_MAP[arg], None
            # Otherwise treat as entity forward ref
            return FieldType.ENTITY_REF, arg

        # Primitive Python type
        if arg in _PY_TYPE_MAP:
            return _PY_TYPE_MAP[arg], None

        # datetime special case (imported at call site)
        import datetime as _dt

        if arg is _dt.datetime:
            return FieldType.DATETIME, None

        # Entity subclass (direct class reference)
        # We can't import Entity here to avoid circular imports, so check by name
        if isinstance(arg, type) and hasattr(arg, "_meta"):
            return FieldType.ENTITY_REF, arg.__name__

        raise ValueError(
            f"Field '{self.name}': unsupported type annotation {arg!r}. "
            "Use str, int, float, datetime, or a forward ref string to another Entity."
        )


class ManyToOneField(_BitemporalField, relationship=RelationshipType.MANY_TO_ONE):
    """Many entities can share the same value (e.g., city). One value per entity at any time."""


class OneToOneField(_BitemporalField, relationship=RelationshipType.ONE_TO_ONE):
    """Exactly one value per entity at any given point in time."""


class OneToManyField(_BitemporalField, relationship=RelationshipType.ONE_TO_MANY):
    """Multiple values per entity at the same time (e.g., directors). Returns exploded rows."""


# Convenience tuple for isinstance checks
FIELD_TYPES = (ManyToOneField, OneToOneField, OneToManyField)


# ---------------------------------------------------------------------------
# FieldSpec — resolved field metadata (set by EntityMeta)
# ---------------------------------------------------------------------------


class FieldSpec:
    """Fully resolved field metadata attached to EntityOptions."""

    def __init__(
        self,
        name: str,
        relationship: RelationshipType,
        sql_type: FieldType,
        entity_ref: str | None,  # non-None when sql_type == ENTITY_REF
    ) -> None:
        self.name = name
        self.relationship = relationship
        self.sql_type = sql_type
        self.entity_ref = entity_ref  # name of referenced entity class

    @property
    def sql_type_str(self) -> str:
        return self.sql_type.value

    def __repr__(self) -> str:
        return (
            f"FieldSpec(name={self.name!r}, relationship={self.relationship.value}, "
            f"sql_type={self.sql_type_str!r}, entity_ref={self.entity_ref!r})"
        )


def to_snake_case(name: str) -> str:
    """Convert CamelCase to snake_case."""
    s = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", name)
    s = re.sub(r"([a-z\d])([A-Z])", r"\1_\2", s)
    return s.lower()
