from pydantic import BaseModel


class RequestContext(BaseModel):
    request_id: str
    service: str
