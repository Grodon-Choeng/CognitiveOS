from piccolo.conf.apps import AppConfig, AppRegistry
from piccolo.engine.sqlite import SQLiteEngine

from app.models import (
    EmbeddingRecord,
    KnowledgeItem,
    Memory,
    Prompt,
    PromptTemplate,
    Reminder,
    Sessions,
)

DB = SQLiteEngine(path="cognitive.db")

APP_CONFIG = AppConfig(
    app_name="cognitive",
    migrations_folder_path="piccolo_migrations",
    table_classes=[
        KnowledgeItem,
        Prompt,
        PromptTemplate,
        Memory,
        EmbeddingRecord,
        Reminder,
        Sessions,
    ],
)

APP_REGISTRY = AppRegistry(
    apps=[
        "piccolo.apps.user.piccolo_app",
        "piccolo_conf",
    ]
)
