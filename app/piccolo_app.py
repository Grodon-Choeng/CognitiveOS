from piccolo.conf.apps import AppConfig

from .models.knowledge_item import KnowledgeItem
from .models.prompt import Prompt


APP_CONFIG = AppConfig(
    app_name="cognitive",
    migrations_folder_path="piccolo_migrations",
    table_classes=[KnowledgeItem, Prompt],
)
