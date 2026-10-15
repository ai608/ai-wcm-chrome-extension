from typing import Any

import orjson
from starlette.responses import Response


class OrjsonResponse(Response):
    media_type = "application/json"

    def render(self, content: Any) -> bytes:
        return orjson.dumps(content)
