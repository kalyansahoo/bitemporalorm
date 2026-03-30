"""
Business entity example — save and filter.

Prerequisites:
  export DATABASE_URL="postgresql://postgres:secret@localhost:5432/bitemporalorm_dev"
  bitemporalorm make_migration --models examples.business_entity.models
  bitemporalorm migrate --db-url $DATABASE_URL
"""

import asyncio
from datetime import datetime, timezone

import polars as pl

from bitemporalorm import ConnectionConfig, DBExecutor, register_executor
from examples.business_entity.models import BusinessEntity


async def main() -> None:
    # -------------------------------------------------------------------------
    # 1. Connect
    # -------------------------------------------------------------------------
    config = ConnectionConfig(
        host="localhost",
        port=5432,
        database="bitemporalorm_dev",
        user="postgres",
        password="secret",
    )
    executor = DBExecutor(config)
    register_executor(executor)
    await executor.connect()

    try:
        # -------------------------------------------------------------------------
        # 2. Insert two new entities (no entity_id → auto-assigned)
        #    Both become effective from 2020-01-01 onwards (no end → infinity).
        # -------------------------------------------------------------------------
        df_insert = pl.DataFrame({
            "as_of_start":    [datetime(2020, 1, 1, tzinfo=timezone.utc),
                               datetime(2020, 1, 1, tzinfo=timezone.utc),
                               datetime(2020, 1, 1, tzinfo=timezone.utc)],
            "city":           ["London",      "Paris",       "London"],
            "phone_number":   ["+44123456789", "+33987654321", "+44111111111"],
            # director is one-to-many: pass one row per (entity, director) pair
            # We give entity 0 (London) two directors, entity 1 (Paris) one.
            # For a clean insert we use separate save() calls per entity:
        })
        # Save London entity with two directors
        london_df = await BusinessEntity.save(pl.DataFrame({
            "as_of_start":  [datetime(2020, 1, 1, tzinfo=timezone.utc),
                             datetime(2020, 1, 1, tzinfo=timezone.utc)],
            "city":         ["London",  "London"],
            "phone_number": ["+44123456789", "+44123456789"],
            "director":     ["Alice Smith", "Bob Jones"],
        }))
        london_id = london_df["entity_id"][0]
        print(f"London entity created with id={london_id}")

        # Save Paris entity with one director
        paris_df = await BusinessEntity.save(pl.DataFrame({
            "as_of_start":  [datetime(2020, 1, 1, tzinfo=timezone.utc)],
            "city":         ["Paris"],
            "phone_number": ["+33987654321"],
            "director":     ["Claire Dupont"],
        }))
        paris_id = paris_df["entity_id"][0]
        print(f"Paris entity created with id={paris_id}")

        # -------------------------------------------------------------------------
        # 3. Retroactive update — London moved to Manchester from 2022-06-01
        # -------------------------------------------------------------------------
        await BusinessEntity.save(pl.DataFrame({
            "entity_id":    [london_id],
            "as_of_start":  [datetime(2022, 6, 1, tzinfo=timezone.utc)],
            "city":         ["Manchester"],
        }))
        print("Updated London → Manchester from 2022-06-01")

        # -------------------------------------------------------------------------
        # 4. Point-in-time query — state as of 2021-01-01
        #    London should still show city=London at this point.
        # -------------------------------------------------------------------------
        df_2021 = await BusinessEntity.filter(
            as_of=datetime(2021, 1, 1, tzinfo=timezone.utc),
        )
        print("\n--- State as of 2021-01-01 ---")
        print(df_2021)

        # -------------------------------------------------------------------------
        # 5. Point-in-time query — state as of 2023-01-01
        #    London entity should now show city=Manchester.
        # -------------------------------------------------------------------------
        df_2023 = await BusinessEntity.filter(
            as_of=datetime(2023, 1, 1, tzinfo=timezone.utc),
        )
        print("\n--- State as of 2023-01-01 ---")
        print(df_2023)

        # -------------------------------------------------------------------------
        # 6. Filtered query — only entities in Manchester as of 2023
        # -------------------------------------------------------------------------
        df_manchester = await BusinessEntity.filter(
            as_of=datetime(2023, 1, 1, tzinfo=timezone.utc),
            pl.col("city") == "Manchester",
        )
        print("\n--- Manchester entities as of 2023-01-01 ---")
        print(df_manchester)

    finally:
        await executor.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
