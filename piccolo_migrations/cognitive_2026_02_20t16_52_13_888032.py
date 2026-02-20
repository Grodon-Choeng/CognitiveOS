from piccolo.apps.migrations.auto.migration_manager import MigrationManager
from piccolo.columns.column_types import UUID, Boolean, Integer, Serial, Text, Timestamp, Varchar
from piccolo.columns.defaults.timestamp import TimestampNow
from piccolo.columns.defaults.uuid import UUID4
from piccolo.columns.indexes import IndexMethod

from app.utils.times import utc_time

ID = "2026-02-20T16:52:13:888032"
VERSION = "1.32.0"
DESCRIPTION = ""


async def forwards():
    manager = MigrationManager(migration_id=ID, app_name="cognitive", description=DESCRIPTION)

    manager.add_table(class_name="Reminder", tablename="reminder", schema=None, columns=None)

    manager.add_column(
        table_class_name="Reminder",
        tablename="reminder",
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
            "db_column_name": None,
            "secret": False,
        },
        schema=None,
    )

    manager.add_column(
        table_class_name="Reminder",
        tablename="reminder",
        column_name="uuid",
        db_column_name="uuid",
        column_class_name="UUID",
        column_class=UUID,
        params={
            "default": UUID4(),
            "null": False,
            "primary_key": False,
            "unique": False,
            "index": True,
            "index_method": IndexMethod.btree,
            "choices": None,
            "db_column_name": None,
            "secret": False,
        },
        schema=None,
    )

    manager.add_column(
        table_class_name="Reminder",
        tablename="reminder",
        column_name="created_at",
        db_column_name="created_at",
        column_class_name="Timestamp",
        column_class=Timestamp,
        params={
            "default": utc_time,
            "null": False,
            "primary_key": False,
            "unique": False,
            "index": True,
            "index_method": IndexMethod.btree,
            "choices": None,
            "db_column_name": None,
            "secret": False,
        },
        schema=None,
    )

    manager.add_column(
        table_class_name="Reminder",
        tablename="reminder",
        column_name="updated_at",
        db_column_name="updated_at",
        column_class_name="Timestamp",
        column_class=Timestamp,
        params={
            "default": utc_time,
            "null": False,
            "primary_key": False,
            "unique": False,
            "index": True,
            "index_method": IndexMethod.btree,
            "choices": None,
            "db_column_name": None,
            "secret": False,
        },
        schema=None,
    )

    manager.add_column(
        table_class_name="Reminder",
        tablename="reminder",
        column_name="content",
        db_column_name="content",
        column_class_name="Text",
        column_class=Text,
        params={
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
        table_class_name="Reminder",
        tablename="reminder",
        column_name="remind_at",
        db_column_name="remind_at",
        column_class_name="Timestamp",
        column_class=Timestamp,
        params={
            "default": TimestampNow(),
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
        table_class_name="Reminder",
        tablename="reminder",
        column_name="user_id",
        db_column_name="user_id",
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
        table_class_name="Reminder",
        tablename="reminder",
        column_name="channel_id",
        db_column_name="channel_id",
        column_class_name="Integer",
        column_class=Integer,
        params={
            "default": 0,
            "null": True,
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
        table_class_name="Reminder",
        tablename="reminder",
        column_name="guild_id",
        db_column_name="guild_id",
        column_class_name="Integer",
        column_class=Integer,
        params={
            "default": 0,
            "null": True,
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
        table_class_name="Reminder",
        tablename="reminder",
        column_name="is_sent",
        db_column_name="is_sent",
        column_class_name="Boolean",
        column_class=Boolean,
        params={
            "default": False,
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
        table_class_name="Reminder",
        tablename="reminder",
        column_name="sent_at",
        db_column_name="sent_at",
        column_class_name="Timestamp",
        column_class=Timestamp,
        params={
            "default": None,
            "null": True,
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
        table_class_name="Reminder",
        tablename="reminder",
        column_name="provider",
        db_column_name="provider",
        column_class_name="Varchar",
        column_class=Varchar,
        params={
            "length": 20,
            "default": "discord",
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

    manager.alter_column(
        table_class_name="KnowledgeItem",
        tablename="knowledge_item",
        column_name="created_at",
        db_column_name="created_at",
        params={"index": True},
        old_params={"index": False},
        column_class=Timestamp,
        old_column_class=Timestamp,
        schema=None,
    )

    manager.alter_column(
        table_class_name="KnowledgeItem",
        tablename="knowledge_item",
        column_name="updated_at",
        db_column_name="updated_at",
        params={"index": True},
        old_params={"index": False},
        column_class=Timestamp,
        old_column_class=Timestamp,
        schema=None,
    )

    manager.alter_column(
        table_class_name="Prompt",
        tablename="prompt",
        column_name="created_at",
        db_column_name="created_at",
        params={"index": True},
        old_params={"index": False},
        column_class=Timestamp,
        old_column_class=Timestamp,
        schema=None,
    )

    manager.alter_column(
        table_class_name="Prompt",
        tablename="prompt",
        column_name="updated_at",
        db_column_name="updated_at",
        params={"index": True},
        old_params={"index": False},
        column_class=Timestamp,
        old_column_class=Timestamp,
        schema=None,
    )

    return manager
