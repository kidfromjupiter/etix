from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class SeatCreate(BaseModel):
    eventUrl: str
    section: str
    row: str
    seat: str
    price: float
    info: Optional[str] = None

class EventCreate(BaseModel):
    name: str
    url: str
    date: datetime
    venue: str
