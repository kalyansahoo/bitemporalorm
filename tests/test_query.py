from datetime import datetime, timezone

import polars as pl
import pytest

from bitemporalorm.entity import Entity
from bitemporalorm.fields import ManyToOneField, OneToManyField, OneToOneField
from bitemporalorm.query.builder import FilterError, build_filter_sql
from bitemporalorm.registry import registry


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

AS_OF = datetime(2025, 6, 1, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# SQL generation — basic
# ---------------------------------------------------------------------------

def test_filter_sql_selects_entity_id():
    class Org(Entity):
        city: ManyToOneField[str]

    sql, _ = build_filter_sql(Org, AS_OF, [])
    assert "entity_id" in sql


def test_filter_sql_joins_field_table():
    class Corp(Entity):
        region: ManyToOneField[str]

    sql, _ = build_filter_sql(Corp, AS_OF, [])
    assert "corp_to_region" in sql


def test_filter_sql_contains_as_of():
    class Firm(Entity):
        city: ManyToOneField[str]

    sql, _ = build_filter_sql(Firm, AS_OF, [])
    as_of_str = AS_OF.isoformat()
    assert as_of_str in sql
    assert "@>" in sql


def test_filter_sql_multiple_fields():
    class Enterprise(Entity):
        city:    ManyToOneField[str]
        phone:   OneToOneField[str]
        manager: OneToManyField[str]

    sql, _ = build_filter_sql(Enterprise, AS_OF, [])
    assert "enterprise_to_city" in sql
    assert "enterprise_to_phone" in sql
    assert "enterprise_to_manager" in sql


# ---------------------------------------------------------------------------
# ExprTranslator — equality filter
# ---------------------------------------------------------------------------

def test_filter_expr_equality():
    class Bank(Entity):
        city: ManyToOneField[str]

    sql, _ = build_filter_sql(Bank, AS_OF, [pl.col("city") == "London"])
    assert "London" in sql


def test_filter_expr_greater_than():
    class Fund(Entity):
        score: ManyToOneField[int]

    sql, _ = build_filter_sql(Fund, AS_OF, [pl.col("score") > 50])
    assert "50" in sql


def test_filter_expr_and():
    class Group(Entity):
        city:  ManyToOneField[str]
        score: ManyToOneField[int]

    sql, _ = build_filter_sql(
        Group, AS_OF,
        [(pl.col("city") == "Paris") & (pl.col("score") > 10)]
    )
    assert "Paris" in sql
    assert "10" in sql


# ---------------------------------------------------------------------------
# Inheritance — SQL includes parent field tables
# ---------------------------------------------------------------------------

def test_filter_sql_includes_parent_fields():
    class BaseOrg(Entity):
        city: ManyToOneField[str]

    class SubOrg(BaseOrg):
        branch: OneToOneField[str]

    sql, _ = build_filter_sql(SubOrg, AS_OF, [])
    # Should join parent field table and child field table
    assert "base_org_to_city" in sql
    assert "sub_org_to_branch" in sql
    # Should join hierarchy table
    assert "sub_org_to_parent_entity" in sql


# ---------------------------------------------------------------------------
# Unknown column raises FilterError
# ---------------------------------------------------------------------------

def test_filter_unknown_column_raises():
    class Small(Entity):
        city: ManyToOneField[str]

    with pytest.raises(FilterError, match="Unknown column"):
        build_filter_sql(Small, AS_OF, [pl.col("nonexistent") == "x"])
