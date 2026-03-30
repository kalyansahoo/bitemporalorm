import os
import tempfile
import pytest

from bitemporalorm.entity import Entity
from bitemporalorm.fields import ManyToOneField, OneToManyField, OneToOneField
from bitemporalorm.migration.differ import MigrationError, SchemaDiffer
from bitemporalorm.migration.loader import MigrationLoader
from bitemporalorm.migration.ops import (
    CreateEntityTable,
    CreateFieldTables,
    CreateHierarchyTable,
    DropEntityTable,
    DropFieldTables,
)
from bitemporalorm.migration.state import (
    EntitySnapshot,
    FieldSnapshot,
    MigrationState,
)
from bitemporalorm.migration.writer import MigrationWriter
from bitemporalorm.registry import registry


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _state_with_entity(name, table, fields=None, parent=None):
    state = MigrationState()
    state.entities[name] = EntitySnapshot(
        name=name,
        table_name=table,
        fields=fields or {},
        parent_entity=parent,
    )
    return state


def _field(name, sql_type="TEXT", rel="many_to_one", entity_ref=None):
    return FieldSnapshot(name=name, sql_type=sql_type, relationship=rel, entity_ref=entity_ref)


# ---------------------------------------------------------------------------
# MigrationState.from_registry
# ---------------------------------------------------------------------------

def test_state_from_registry():
    class Firm(Entity):
        city: ManyToOneField[str]

    registry.register(Firm)
    state = MigrationState.from_registry()
    assert "Firm" in state.entities
    snap = state.entities["Firm"]
    assert snap.table_name == "firm"
    assert "city" in snap.fields
    assert snap.fields["city"].sql_type == "TEXT"


# ---------------------------------------------------------------------------
# SchemaDiffer — new entity
# ---------------------------------------------------------------------------

def test_differ_new_entity():
    old = MigrationState()
    new = MigrationState()
    new.entities["Company"] = EntitySnapshot(
        name="Company",
        table_name="company",
        fields={"city": _field("city")},
    )

    ops = SchemaDiffer().diff(old, new)
    types = [type(o).__name__ for o in ops]
    assert "CreateEntityTable" in types
    assert "CreateFieldTables" in types


def test_differ_new_entity_with_hierarchy():
    old = MigrationState()
    new = MigrationState()
    new.entities["Base"] = EntitySnapshot(name="Base", table_name="base", fields={})
    new.entities["Child"] = EntitySnapshot(
        name="Child", table_name="child",
        fields={"code": _field("code")},
        parent_entity="Base",
    )

    ops = SchemaDiffer().diff(old, new)
    types = [type(o).__name__ for o in ops]
    assert "CreateHierarchyTable" in types


# ---------------------------------------------------------------------------
# SchemaDiffer — drop entity
# ---------------------------------------------------------------------------

def test_differ_drop_entity():
    old = _state_with_entity("OldCo", "old_co", {"name": _field("name")})
    new = MigrationState()

    ops = SchemaDiffer().diff(old, new)
    assert any(isinstance(o, DropEntityTable) for o in ops)


# ---------------------------------------------------------------------------
# SchemaDiffer — add field
# ---------------------------------------------------------------------------

def test_differ_add_field():
    old = _state_with_entity("Biz", "biz", {"city": _field("city")})
    new = _state_with_entity("Biz", "biz", {
        "city":  _field("city"),
        "phone": _field("phone"),
    })

    ops = SchemaDiffer().diff(old, new)
    new_field_ops = [o for o in ops if isinstance(o, CreateFieldTables)]
    field_names = [o.field_name for o in new_field_ops]
    assert "phone" in field_names
    assert "city" not in field_names


# ---------------------------------------------------------------------------
# SchemaDiffer — drop field
# ---------------------------------------------------------------------------

def test_differ_drop_field():
    old = _state_with_entity("Biz", "biz", {"city": _field("city"), "phone": _field("phone")})
    new = _state_with_entity("Biz", "biz", {"city": _field("city")})

    ops = SchemaDiffer().diff(old, new)
    drop_ops = [o for o in ops if isinstance(o, DropFieldTables)]
    assert any(o.field_name == "phone" for o in drop_ops)


# ---------------------------------------------------------------------------
# SchemaDiffer — type change raises MigrationError
# ---------------------------------------------------------------------------

def test_differ_type_change_raises():
    old = _state_with_entity("Co", "co", {"score": _field("score", sql_type="TEXT")})
    new = _state_with_entity("Co", "co", {"score": _field("score", sql_type="BIGINT")})

    with pytest.raises(MigrationError, match="Cannot change type"):
        SchemaDiffer().diff(old, new)


# ---------------------------------------------------------------------------
# SchemaDiffer — parent change raises MigrationError
# ---------------------------------------------------------------------------

def test_differ_parent_change_raises():
    old = _state_with_entity("Child", "child", {}, parent="ParentA")
    new = _state_with_entity("Child", "child", {}, parent="ParentB")
    # Add parent entities to avoid missing reference error
    old.entities["ParentA"] = EntitySnapshot(name="ParentA", table_name="parent_a")
    new.entities["ParentB"] = EntitySnapshot(name="ParentB", table_name="parent_b")

    with pytest.raises(MigrationError, match="Cannot change parent"):
        SchemaDiffer().diff(old, new)


# ---------------------------------------------------------------------------
# Operations SQL
# ---------------------------------------------------------------------------

def test_create_entity_table_sql():
    op = CreateEntityTable("Company", "company")
    sql = op.to_sql()
    assert 'CREATE TABLE IF NOT EXISTS "company"' in sql
    assert "BIGSERIAL" in sql


def test_create_field_tables_sql_many_to_one():
    op = CreateFieldTables(
        entity_name="Company",
        entity_table="company",
        field_name="city",
        sql_type="TEXT",
        relationship="many_to_one",
    )
    sql = op.to_sql()
    assert '"company_to_city_audit"' in sql
    assert '"company_to_city"' in sql
    assert "TSTZRANGE" in sql
    assert "EXCLUDE USING GIST" in sql


def test_create_field_tables_sql_one_to_many_no_exclude():
    op = CreateFieldTables(
        entity_name="Company",
        entity_table="company",
        field_name="director",
        sql_type="TEXT",
        relationship="one_to_many",
    )
    sql = op.to_sql()
    # No exclusion constraint for one-to-many
    assert "EXCLUDE USING GIST" not in sql
    assert '"company_to_director"' in sql


def test_create_hierarchy_table_sql():
    op = CreateHierarchyTable(
        entity_name="Child",
        entity_table="child",
        parent_entity_name="Parent",
        parent_table="parent",
    )
    sql = op.to_sql()
    assert '"child_to_parent_entity"' in sql
    assert '"parent"("id")' in sql
    assert "EXCLUDE USING GIST" in sql


# ---------------------------------------------------------------------------
# MigrationWriter + MigrationLoader round-trip
# ---------------------------------------------------------------------------

def test_writer_creates_file():
    with tempfile.TemporaryDirectory() as tmpdir:
        ops = [CreateEntityTable("Company", "company")]
        writer = MigrationWriter(tmpdir)
        path = writer.write("initial", ops, [])
        assert os.path.exists(path)
        assert "0001_initial.py" in path


def test_loader_round_trip():
    with tempfile.TemporaryDirectory() as tmpdir:
        ops = [CreateEntityTable("Company", "company")]
        writer = MigrationWriter(tmpdir)
        writer.write("initial", ops, [])

        loader = MigrationLoader(tmpdir)
        loaded = loader.load()
        assert len(loaded) == 1
        assert loaded[0].name == "0001_initial"
        assert len(loaded[0].operations) == 1
        assert isinstance(loaded[0].operations[0], CreateEntityTable)


def test_loader_topological_sort():
    with tempfile.TemporaryDirectory() as tmpdir:
        writer = MigrationWriter(tmpdir)
        p1 = writer.write("initial", [CreateEntityTable("A", "a")], [])
        p2 = writer.write("second", [CreateEntityTable("B", "b")], ["0001_initial"])

        loader = MigrationLoader(tmpdir)
        loaded = loader.load()
        names = [m.name for m in loaded]
        assert names.index("0001_initial") < names.index("0002_second")


# ---------------------------------------------------------------------------
# from_migration_history
# ---------------------------------------------------------------------------

def test_from_migration_history():
    with tempfile.TemporaryDirectory() as tmpdir:
        writer = MigrationWriter(tmpdir)
        writer.write("initial", [
            CreateEntityTable("Company", "company"),
            CreateFieldTables(
                entity_name="Company",
                entity_table="company",
                field_name="city",
                sql_type="TEXT",
                relationship="many_to_one",
            ),
        ], [])

        state = MigrationState.from_migration_history(tmpdir)
        assert "Company" in state.entities
        assert "city" in state.entities["Company"].fields
