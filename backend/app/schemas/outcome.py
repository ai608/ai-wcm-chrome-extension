from pydantic import BaseModel, Field


class SaveOutcome(BaseModel):
    outcome_id: str = Field(min_length=1, max_length=64)
    note: str = Field(default="", max_length=2000)
    booked: bool = False
