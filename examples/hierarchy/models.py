"""
Hierarchy example — single-class inheritance.

RegionalOffice extends BusinessEntity, inheriting city / phone_number / director.
It adds its own branch_code and head_count fields.

The parent-child link between a RegionalOffice instance and its parent
BusinessEntity instance is stored (bitemporally) in:

  regional_office_to_parent_entity   -- tstzrange as_of, EXCLUDE GIST

When you call RegionalOffice.filter(as_of=...), the query JOINs:
  - regional_office fields (branch_code, head_count)
  - regional_office_to_parent_entity to get the parent entity id
  - business_entity fields (city, phone_number, director) via the parent id

Tables created by make_migration / migrate:

  regional_office
  regional_office_to_branch_code[_audit]
  regional_office_to_head_count[_audit]
  regional_office_to_parent_entity          -- hierarchy link
"""

from bitemporalorm import Entity, ManyToOneField, OneToManyField, OneToOneField


class BusinessEntity(Entity):
    city:         ManyToOneField[str]
    phone_number: OneToOneField[str]
    director:     OneToManyField[str]


class RegionalOffice(BusinessEntity):
    """A regional office is a child entity of BusinessEntity.

    It has its own branch_code (unique per office) and head_count,
    plus inherits city / phone_number / director from the parent entity.
    """
    branch_code: OneToOneField[str]
    head_count:  ManyToOneField[int]
