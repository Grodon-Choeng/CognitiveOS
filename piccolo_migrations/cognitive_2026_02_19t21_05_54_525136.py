from piccolo.apps.migrations.auto.migration_manager import MigrationManager
from piccolo.columns.column_types import Integer
from piccolo.columns.column_types import Serial
from piccolo.columns.column_types import Timestamp
from piccolo.columns.column_types import Varchar
from piccolo.columns.defaults.timestamp import TimestampOffset
from piccolo.columns.indexes import IndexMethod

ID = "2026-02-19T21:05:54:525136"
VERSION = "1.32.0"
DESCRIPTION = ""


async def forwards():
    manager = MigrationManager(
        migration_id=ID, app_name="cognitive", description=DESCRIPTION
    )

    manager.add_table(
        class_name="Sessions", tablename="sessions", schema=None, columns=None
    )

    manager.add_column(
        table_class_name="Sessions",
        tablename="sessions",
        column_name="token",
        db_column_name="token",
        column_class_name="Varchar",
        column_class=Varchar,
        params={
            "length": 100,
            "default": "",
            "null": False,
            "primary_key": False,
            "unique": False,
            "index": False,
            "index_method": IndexMethod.btree,
            "choices": None,
            "db_column_name": None,
            "secret": False,
        },
        schema=None,
    )

    manager.add_column(
        table_class_name="Sessions",
        tablename="sessions",
        column_name="user_id",
        db_column_name="user_id",
        column_class_name="Integer",
        column_class=Integer,
        params={
            "default": 0,
            "null": False,
            "primary_key": False,
            "unique": False,
            "index": False,
            "index_method": IndexMethod.btree,
            "choices": None,
            "db_column_name": None,
            "secret": False,
        },
        schema=None,
    )

    manager.add_column(
        table_class_name="Sessions",
        tablename="sessions",
        column_name="expiry_date",
        db_column_name="expiry_date",
        column_class_name="Timestamp",
        column_class=Timestamp,
        params={
            "default": TimestampOffset(days=0, hours=1, minutes=0, seconds=0),
            "null": False,
            "primary_key": False,
            "unique": False,
            "index": False,
            "index_method": IndexMethod.btree,
            "choices": None,
            "db_column_name": None,
            "secret": False,
        },
        schema=None,
    )

    manager.add_column(
        table_class_name="Sessions",
        tablename="sessions",
        column_name="max_expiry_date",
        db_column_name="max_expiry_date",
        column_class_name="Timestamp",
        column_class=Timestamp,
        params={
            "default": TimestampOffset(days=7, hours=0, minutes=0, seconds=0),
            "null": False,
            "primary_key": False,
            "unique": False,
            "index": False,
            "index_method": IndexMethod.btree,
            "choices": None,
            "db_column_name": None,
            "secret": False,
        },
        schema=None,
    )

    manager.add_column(
        table_class_name="Sessions",
        tablename="sessions",
        column_name="id",
        db_column_name="id",
        column_class_name="Serial",
        column_class=Serial,
        params={
            "null": False,
            "primary_key": True,
            "unique": False,
            "index": False,
            "index_method": IndexMethod.btree,
            "choices": None,
            "db_column_name": "id",
            "secret": False,
        },
        schema=None,
    )

    return manager
