from piccolo_admin.endpoints import create_admin

from piccolo_conf import APP_CONFIG

tables = APP_CONFIG.table_classes

app = create_admin(tables=tables)
