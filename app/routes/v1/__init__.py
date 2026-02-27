from litestar import Router

from .health import HealthController
from .im import IMController
from .items import ItemsController
from .prompts import PromptsController
from .retrieval import RetrievalController
from .webhook import WebhookController

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
