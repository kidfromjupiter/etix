from pydantic import BaseModel, RootModel
from typing import Optional, Any, Dict
from datetime import datetime

from pydantic import BaseModel
from typing import Optional, List

class AdjacentSeatsResponse(BaseModel):
    row_id: int
    row_name: str
    section_id: int
    section_name: str
    seat_count: int
    seats: List[Dict[str, Any]]
    price_levels: List[Dict[str, Any]]
    total_price: float
    average_price: float

class TicketDataIngest(BaseModel):
    event_id: int
    all: Dict[str, Any]
    available: List[Dict[str, Any]]
    availableByRow: Dict[str, List[Dict[str, Any]]]
    availableByPrice: Dict[str, List[Dict[str, Any]]]
    adjacentSeats: List[Dict[str, Any]]
    adjacentByCount: Dict[int, List[Dict[str, Any]]]
    summary: Dict[str, Any]
    map: List[str]
    statusLegend: Dict[str, str]
    section: str

class EventCreate(BaseModel):
    name: str
    date: str

class RawData(RootModel[Any]):
    pass
