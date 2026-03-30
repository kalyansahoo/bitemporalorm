import datetime
import pytest

from bitemporalorm.fields import (
    FieldType,
    ManyToOneField,
    OneToManyField,
    OneToOneField,
    RelationshipType,
    _BitemporalField,
    to_snake_case,
)


# ---------------------------------------------------------------------------
# to_snake_case
# ---------------------------------------------------------------------------

def test_to_snake_case_simple():
    assert to_snake_case("BusinessEntity") == "business_entity"

def test_to_snake_case_already_snake():
    assert to_snake_case("business_entity") == "business_entity"

def test_to_snake_case_acronym():
    assert to_snake_case("HTMLParser") == "html_parser"


# ---------------------------------------------------------------------------
# Field class-getitem syntax
# ---------------------------------------------------------------------------

def test_many_to_one_field_str():
    f = ManyToOneField[str]
    assert isinstance(f, ManyToOneField)
    assert f._type_arg is str
    assert f.relationship == RelationshipType.MANY_TO_ONE


def test_one_to_one_field_int():
    f = OneToOneField[int]
    assert isinstance(f, OneToOneField)
    assert f._type_arg is int
    assert f.relationship == RelationshipType.ONE_TO_ONE


def test_one_to_many_field_float():
    f = OneToManyField[float]
    assert isinstance(f, OneToManyField)
    assert f.relationship == RelationshipType.ONE_TO_MANY


# ---------------------------------------------------------------------------
# _resolve_field_type
# ---------------------------------------------------------------------------

def _make_field(cls, type_arg):
    f = cls.__new__(cls)
    f._type_arg = type_arg
    f.name = "test_field"
    return f


def test_resolve_str():
    f = _make_field(ManyToOneField, str)
    ft, ref = f._resolve_field_type(None)
    assert ft == FieldType.TEXT
    assert ref is None


def test_resolve_int():
    f = _make_field(ManyToOneField, int)
    ft, ref = f._resolve_field_type(None)
    assert ft == FieldType.INT
    assert ref is None


def test_resolve_float():
    f = _make_field(ManyToOneField, float)
    ft, ref = f._resolve_field_type(None)
    assert ft == FieldType.FLOAT
    assert ref is None


def test_resolve_datetime():
    f = _make_field(ManyToOneField, datetime.datetime)
    ft, ref = f._resolve_field_type(None)
    assert ft == FieldType.DATETIME
    assert ref is None


def test_resolve_string_forward_ref():
    f = _make_field(ManyToOneField, "SomeEntity")
    ft, ref = f._resolve_field_type(None)
    assert ft == FieldType.ENTITY_REF
    assert ref == "SomeEntity"


def test_resolve_string_primitive_name():
    f = _make_field(ManyToOneField, "str")
    ft, ref = f._resolve_field_type(None)
    assert ft == FieldType.TEXT
    assert ref is None


def test_resolve_unsupported_raises():
    f = _make_field(ManyToOneField, list)
    with pytest.raises(ValueError, match="unsupported type annotation"):
        f._resolve_field_type(None)
