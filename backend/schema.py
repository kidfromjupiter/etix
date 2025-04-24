from pydantic import BaseModel, RootModel
from typing import Optional, Any, Dict
from datetime import datetime

from pydantic import BaseModel
from typing import Optional, List

class PriceCode(BaseModel):
    id: int
    name: str
    description: str

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
    priceCode: PriceCode

class RowData(BaseModel):
    row: str
    seats: List[Seat]
    count: int
    priceRange: dict  # can define a model if you need stricter validation

class SeatingIngestRequest(BaseModel):
    event_id: str
    rows: List[RowData]
# used only for debug
class RawData(RootModel[Any]):
    pass
