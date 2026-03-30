"""
Business entity example models.

BusinessEntity has three bitemporal fields:
  - city         (many-to-one): many businesses can share the same city value
  - phone_number (one-to-one):  one number per business at any point in time
  - director     (one-to-many): multiple directors per business → exploded rows

Tables created by `bitemporalorm make_migration && bitemporalorm migrate`:

  business_entity                      -- root entity table
  business_entity_to_city              -- materialized (non-overlapping tstzrange)
  business_entity_to_city_audit        -- immutable event log
  business_entity_to_phone_number      -- materialized
  business_entity_to_phone_number_audit
  business_entity_to_director          -- materialized (no EXCLUDE — one-to-many)
  business_entity_to_director_audit
"""

from bitemporalorm import Entity, ManyToOneField, OneToManyField, OneToOneField


class BusinessEntity(Entity):
    city:         ManyToOneField[str]
    phone_number: OneToOneField[str]
    director:     OneToManyField[str]
