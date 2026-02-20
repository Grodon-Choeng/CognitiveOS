from litestar import Router

from app.routes.v1.health import HealthController
from app.routes.v1.im import IMController
from app.routes.v1.items import ItemsController
from app.routes.v1.prompts import PromptsController
from app.routes.v1.retrieval import RetrievalController
from app.routes.v1.webhook import WebhookController

v1_router = Router(
    path="/api/v1",
    route_handlers=[
        HealthController,
        WebhookController,
        ItemsController,
        IMController,
        RetrievalController,
        PromptsController,
    ],
)
