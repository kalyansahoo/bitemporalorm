from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

import polars as pl

if TYPE_CHECKING:
    from bitemporalorm.entity import Entity


class FilterError(Exception):
    """Raised when a Polars expression cannot be translated to SQL."""


# ---------------------------------------------------------------------------
# ExprTranslator — pl.Expr → SQL string
# ---------------------------------------------------------------------------

class ExprTranslator:
    """
    Walks the Polars JSON AST and produces a SQL WHERE fragment (string).

    alias_map: field_name → qualified table alias, e.g. {"city": "f_city"}.
    The column value lives in alias.value.
    """

    def __init__(self, alias_map: dict[str, str]) -> None:
        self._alias_map = alias_map

    def translate(self, expr: pl.Expr) -> str:
        node = json.loads(expr.meta.serialize(format="json"))
        return self._visit(node)

    def _visit(self, node: Any) -> str:
        if not isinstance(node, dict):
            raise FilterError(f"Unexpected AST node type: {type(node)!r} — {node!r}")

        if len(node) != 1:
            raise FilterError(f"Unexpected AST node structure (expected 1 key): {node!r}")

        kind, payload = next(iter(node.items()))

        # ---- Column -------------------------------------------------------
        if kind == "Column":
            # Polars 1.x: {"Column": "col_name"} (string payload)
            col_name = payload if isinstance(payload, str) else payload.get("name", str(payload))
            alias = self._alias_map.get(col_name)
            if alias:
                return f'"{alias}".value'
            if col_name == "entity_id":
                return "e.id"
            raise FilterError(
                f"Unknown column '{col_name}'. "
                "Must be a declared field name or 'entity_id'."
            )

        # ---- Literal ------------------------------------------------------
        if kind == "Literal":
            # Polars 1.39+: {"Scalar": {"String": "..."}} or {"Dyn": {"Int": ...}}
            # Older Polars:  {"String": "..."} or {"Int": ...} directly in payload
            if isinstance(payload, dict):
                inner = payload.get("Scalar") or payload.get("Dyn") or payload
                if isinstance(inner, dict):
                    if "String" in inner:
                        s = str(inner["String"]).replace("'", "''")
                        return f"'{s}'"
                    if "Int" in inner:
                        return str(inner["Int"])
                    if "Float" in inner:
                        return str(inner["Float"])
                    if "Boolean" in inner:
                        return "TRUE" if inner["Boolean"] else "FALSE"
            if payload is None:
                return "NULL"
            return "NULL"

        # ---- BinaryExpr ---------------------------------------------------
        if kind == "BinaryExpr":
            left  = self._visit(payload["left"])
            right = self._visit(payload["right"])
            op    = payload["op"]
            op_map = {
                "Eq":    "=",
                "NotEq": "!=",
                "Lt":    "<",
                "LtEq":  "<=",
                "Gt":    ">",
                "GtEq":  ">=",
                "And":   "AND",
                "Or":    "OR",
                "Plus":  "+",
                "Minus": "-",
            }
            if op not in op_map:
                raise FilterError(f"Unsupported binary operator: {op!r}")
            return f"({left} {op_map[op]} {right})"

        # ---- Not ----------------------------------------------------------
        if kind == "Not":
            inner_node = payload["expr"] if isinstance(payload, dict) and "expr" in payload else payload
            return f"(NOT {self._visit(inner_node)})"

        # ---- Null checks --------------------------------------------------
        if kind == "IsNull":
            return f"({self._visit(payload)} IS NULL)"

        if kind == "IsNotNull":
            return f"({self._visit(payload)} IS NOT NULL)"

        # ---- IsIn ---------------------------------------------------------
        if kind == "IsIn":
            col_sql = self._visit(payload["expr"])
            vals_sql = ", ".join(self._visit(v) for v in payload["list"])
            return f"({col_sql} IN ({vals_sql}))"

        # ---- Between ------------------------------------------------------
        if kind == "Between":
            col_sql  = self._visit(payload["expr"])
            low_sql  = self._visit(payload["low"])
            high_sql = self._visit(payload["high"])
            return f"({col_sql} BETWEEN {low_sql} AND {high_sql})"

        # ---- Function (str.contains, str.starts_with, etc.) --------------
        if kind == "Function":
            fn_name = payload.get("name", "").upper()
            args    = [self._visit(a) for a in payload.get("input", payload.get("args", []))]

            if fn_name in ("LOWER", "UPPER", "LENGTH"):
                return f"{fn_name}({args[0]})"

            if fn_name == "CONTAINS" or fn_name == "STR_CONTAINS":
                col, pat = args[0], args[1].strip("'")
                return f"({col} LIKE '%{pat}%')"

            if fn_name == "STARTS_WITH" or fn_name == "STR_STARTS_WITH":
                col, pat = args[0], args[1].strip("'")
                return f"({col} LIKE '{pat}%')"

            if fn_name == "ENDS_WITH" or fn_name == "STR_ENDS_WITH":
                col, pat = args[0], args[1].strip("'")
                return f"({col} LIKE '%{pat}')"

            if fn_name == "TO_LOWERCASE" or fn_name == "STR_TO_LOWERCASE":
                return f"LOWER({args[0]})"

            raise FilterError(f"Unsupported Polars function '{fn_name}' in filter.")

        raise FilterError(f"Unsupported Polars AST node kind: {kind!r}")


# ---------------------------------------------------------------------------
# SQL builder — generates the full SELECT SQL as a string
# ---------------------------------------------------------------------------

def build_filter_sql(
    entity_cls: type[Entity],
    as_of: datetime,
    exprs: list[pl.Expr],
) -> tuple[str, list[Any]]:
    """
    Build a SQL SELECT query for Entity.filter().

    Returns (sql_string, []) — no bind params; as_of is embedded as a literal.
    (connectorx does not support parameterised queries.)
    """
    meta       = entity_cls._meta
    all_fields = meta.all_fields()
    hierarchy  = meta.hierarchy()

    # Safe ISO timestamp literal for PostgreSQL
    if as_of.tzinfo is None:
        as_of = as_of.replace(tzinfo=timezone.utc)
    ts = f"'{as_of.isoformat()}'::timestamptz"

    # alias_map: field_name → JOIN alias (used by ExprTranslator)
    alias_map: dict[str, str] = {fname: f"f_{fname}" for fname in all_fields}

    # ---- SELECT -----------------------------------------------------------
    select_parts: list[str] = [f"e.id AS entity_id"]
    for fname in all_fields:
        alias = alias_map[fname]
        select_parts.append(f'"{alias}".value AS {fname}')

    # ---- FROM -------------------------------------------------------------
    entity_table = meta.table_name
    sql_parts: list[str] = [
        "SELECT " + ", ".join(select_parts),
        f'FROM "{entity_table}" AS e',
    ]

    # ---- Hierarchy JOIN ---------------------------------------------------
    if hierarchy:
        hier_table = f"{entity_table}_to_parent_entity"
        sql_parts.append(
            f'LEFT JOIN "{hier_table}" AS cpe'
            f' ON cpe.entity_id = e.id AND cpe.as_of @> {ts}'
        )

    # ---- Field JOINs -------------------------------------------------------
    for fname in all_fields:
        alias       = alias_map[fname]
        owner_meta  = _find_field_owner_meta(entity_cls, fname)
        field_table = f"{owner_meta.table_name}_to_{fname}"

        # For child entities, parent fields join on cpe.parent_entity_id
        if owner_meta.table_name != entity_table and hierarchy:
            join_id = "cpe.parent_entity_id"
        else:
            join_id = "e.id"

        sql_parts.append(
            f'LEFT JOIN "{field_table}" AS "{alias}"'
            f' ON "{alias}".entity_id = {join_id} AND "{alias}".as_of @> {ts}'
        )

    # ---- WHERE clause from Polars exprs -----------------------------------
    if exprs:
        translator  = ExprTranslator(alias_map)
        conditions  = [translator.translate(e) for e in exprs]
        where_sql   = " AND ".join(conditions)
        sql_parts.append(f"WHERE {where_sql}")

    return "\n".join(sql_parts), []


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _find_field_owner_meta(entity_cls: type[Entity], field_name: str):
    """Walk the MRO to find which entity class declared a given field."""
    from bitemporalorm.entity import EntityMeta

    for cls in entity_cls.__mro__:
        if isinstance(cls, EntityMeta) and cls.__name__ != "Entity":
            if field_name in cls._meta.fields:
                return cls._meta
    return entity_cls._meta
