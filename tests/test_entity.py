import pytest

from bitemporalorm.entity import Entity, EntityOptions
from bitemporalorm.fields import (
    FieldType,
    ManyToOneField,
    OneToManyField,
    OneToOneField,
    RelationshipType,
)
from bitemporalorm.registry import registry


# ---------------------------------------------------------------------------
# Basic entity definition
# ---------------------------------------------------------------------------

def test_entity_registers_in_registry():
    class Company(Entity):
        city: ManyToOneField[str]

    assert registry.get("Company") is Company


def test_entity_table_name_snake_case():
    class LegalEntity(Entity):
        name: ManyToOneField[str]

    assert LegalEntity._meta.table_name == "legal_entity"


def test_entity_custom_table_name():
    class Widget(Entity):
        label: OneToOneField[str]

        class Meta:
            table_name = "custom_widgets"

    assert Widget._meta.table_name == "custom_widgets"


def test_entity_fields_collected():
    class Shop(Entity):
        city:    ManyToOneField[str]
        phone:   OneToOneField[str]
        manager: OneToManyField[str]

    meta = Shop._meta
    assert set(meta.fields.keys()) == {"city", "phone", "manager"}


def test_field_spec_relationship():
    class Store(Entity):
        region:  ManyToOneField[str]
        code:    OneToOneField[int]
        contact: OneToManyField[str]

    assert Store._meta.fields["region"].relationship == RelationshipType.MANY_TO_ONE
    assert Store._meta.fields["code"].relationship   == RelationshipType.ONE_TO_ONE
    assert Store._meta.fields["contact"].relationship == RelationshipType.ONE_TO_MANY


def test_field_spec_sql_type():
    class Office(Entity):
        city:     ManyToOneField[str]
        headcount: ManyToOneField[int]
        revenue:  ManyToOneField[float]

    assert Office._meta.fields["city"].sql_type     == FieldType.TEXT
    assert Office._meta.fields["headcount"].sql_type == FieldType.INT
    assert Office._meta.fields["revenue"].sql_type   == FieldType.FLOAT


# ---------------------------------------------------------------------------
# Single inheritance
# ---------------------------------------------------------------------------

def test_single_inheritance():
    class BaseOrg(Entity):
        city: ManyToOneField[str]

    class SubOrg(BaseOrg):
        branch: OneToOneField[str]

    assert SubOrg._meta.parent_entity is BaseOrg
    # SubOrg has only its own fields
    assert "branch" in SubOrg._meta.fields
    assert "city" not in SubOrg._meta.fields
    # all_fields includes inherited
    assert "city" in SubOrg._meta.all_fields()
    assert "branch" in SubOrg._meta.all_fields()


def test_hierarchy_chain():
    class A(Entity):
        x: ManyToOneField[str]

    class B(A):
        y: ManyToOneField[str]

    class C(B):
        z: ManyToOneField[str]

    assert C._meta.parent_entity is B
    assert C._meta.hierarchy() == [B, A]
    assert set(C._meta.all_fields()) == {"x", "y", "z"}


# ---------------------------------------------------------------------------
# Multiple inheritance forbidden
# ---------------------------------------------------------------------------

def test_multiple_entity_parents_raises():
    class P1(Entity):
        a: ManyToOneField[str]

    class P2(Entity):
        b: ManyToOneField[str]

    with pytest.raises(TypeError, match="multiple entity parents"):
        class Child(P1, P2):
            c: ManyToOneField[str]


# ---------------------------------------------------------------------------
# Entity reference field
# ---------------------------------------------------------------------------

def test_entity_ref_field():
    class Country(Entity):
        code: OneToOneField[str]

    class Business(Entity):
        country: ManyToOneField["Country"]

    fspec = Business._meta.fields["country"]
    assert fspec.sql_type == FieldType.ENTITY_REF
    assert fspec.entity_ref == "Country"
