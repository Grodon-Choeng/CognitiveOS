from piccolo_admin.endpoints import create_admin

from app.piccolo_app import APP_CONFIG

tables = APP_CONFIG.table_classes

print(f"✅ 加载的表：{[t.__name__ for t in tables]}")

app = create_admin(tables=tables)
