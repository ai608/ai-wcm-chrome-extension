from pydantic import BaseModel, Field


class StartAudit(BaseModel):
    url: str = Field(min_length=1, max_length=2048)
    force: bool = False


class LocalCompetitorsRequest(BaseModel):
    query: str | None = Field(default=None, max_length=200)
    location: str | None = Field(default=None, max_length=200)


class AiFullRequest(BaseModel):
    # Your own questions (the writer is skipped). Omit to let the app write them.
    prompts: list[str] | None = Field(default=None, max_length=100)
    n_prompts: int | None = Field(default=None, ge=1, le=100)
    runs: int | None = Field(default=None, ge=1, le=5)


class StartContactResearch(BaseModel):
    force: bool = False
