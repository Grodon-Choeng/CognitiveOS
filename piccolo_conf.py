from piccolo.conf.apps import AppConfig, AppRegistry
from piccolo.engine.sqlite import SQLiteEngine

from app.models.knowledge_item import KnowledgeItem

DB = SQLiteEngine(path="cognitive.db")

APP_CONFIG = AppConfig(
    app_name="cognitive",
    migrations_folder_path="piccolo_migrations",
    table_classes=[KnowledgeItem],
)

APP_REGISTRY = AppRegistry(apps=["piccolo_conf"])
