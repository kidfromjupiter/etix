from pydantic import BaseModel, RootModel
from typing import Optional, Any, Dict
from datetime import datetime

from pydantic import BaseModel
from typing import Optional, List


class Seat(BaseModel):
    rowIndex: int
    seatIndex: int
    row: str
    seat: str
    seatIdentifier: str
    status: str
    currentStatus: str
    realStatus: str
    isAvailable: bool
    note: str
    holdComment: str
    priceLevelId: str
    price: str
    priceNum: str
    priceCode: dict

class Row(BaseModel):
    row: str
    seats: List[Seat]

class SeatingPayload(BaseModel):
    section: str
    rows: List[Row]
    event_id: str
    
class EventCreateRequest(BaseModel):
    url: str
    time: str

class EventResponse(BaseModel):
    event_id: str
    url: str
# used only for debug
class RawData(RootModel[Any]):
    pass
