"""
Hierarchy example — save and filter with inherited fields.

Prerequisites:
  export DATABASE_URL="postgresql://postgres:secret@localhost:5432/bitemporalorm_dev"
  bitemporalorm make_migration --models examples.hierarchy.models
  bitemporalorm migrate --db-url $DATABASE_URL
"""

import asyncio
from datetime import datetime, timezone

import polars as pl

from bitemporalorm import ConnectionConfig, DBExecutor, register_executor
from examples.hierarchy.models import BusinessEntity, RegionalOffice


async def main() -> None:
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
        # 1. Create a parent BusinessEntity (the HQ)
        # -------------------------------------------------------------------------
        hq_df = await BusinessEntity.save(pl.DataFrame({
            "as_of_start":  [datetime(2019, 1, 1, tzinfo=timezone.utc)],
            "city":         ["London"],
            "phone_number": ["+44123456789"],
            "director":     ["Alice Smith"],
        }))
        hq_id = hq_df["entity_id"][0]
        print(f"HQ BusinessEntity id={hq_id}")

        # -------------------------------------------------------------------------
        # 2. Create a RegionalOffice child that points to the HQ parent
        #
        #    The DataFrame must include:
        #      - own fields (branch_code, head_count)
        #      - parent_entity_id column to link to the parent BusinessEntity
        #      - as_of_start (when this relationship/state became effective)
        # -------------------------------------------------------------------------
        office_df = await RegionalOffice.save(pl.DataFrame({
            "as_of_start":       [datetime(2021, 3, 1, tzinfo=timezone.utc)],
            "branch_code":       ["LON-001"],
            "head_count":        [42],
            "parent_entity_id":  [hq_id],
        }))
        office_id = office_df["entity_id"][0]
        print(f"RegionalOffice id={office_id}, parent={hq_id}")

        # -------------------------------------------------------------------------
        # 3. Query RegionalOffice — returns own + inherited fields merged
        #
        #    Result columns: entity_id, branch_code, head_count,
        #                    city, phone_number, director
        # -------------------------------------------------------------------------
        df = await RegionalOffice.filter(
            as_of=datetime(2022, 1, 1, tzinfo=timezone.utc),
        )
        print("\n--- RegionalOffice state as of 2022-01-01 ---")
        print(df)

        # -------------------------------------------------------------------------
        # 4. Filter by inherited field — find offices in London
        # -------------------------------------------------------------------------
        london_offices = await RegionalOffice.filter(
            as_of=datetime(2022, 1, 1, tzinfo=timezone.utc),
            pl.col("city") == "London",
        )
        print("\n--- London offices as of 2022-01-01 ---")
        print(london_offices)

        # -------------------------------------------------------------------------
        # 5. Retroactive parent field change — HQ moves to Manchester from 2023
        #    All child offices that reference this HQ will reflect the change
        #    automatically when queried with as_of >= 2023-01-01.
        # -------------------------------------------------------------------------
        await BusinessEntity.save(pl.DataFrame({
            "entity_id":   [hq_id],
            "as_of_start": [datetime(2023, 1, 1, tzinfo=timezone.utc)],
            "city":        ["Manchester"],
        }))
        print("\nHQ moved to Manchester from 2023-01-01")

        df_2023 = await RegionalOffice.filter(
            as_of=datetime(2023, 6, 1, tzinfo=timezone.utc),
        )
        print("\n--- RegionalOffice state as of 2023-06-01 (HQ now in Manchester) ---")
        print(df_2023)

    finally:
        await executor.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
