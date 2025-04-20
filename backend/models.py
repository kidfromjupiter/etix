import json
from datetime import datetime

from sqlalchemy import Column, Integer, String, Boolean, Float, ForeignKey, Text, DateTime
from sqlalchemy.orm import relationship, declarative_base

Base = declarative_base()

class Event(Base):
    __tablename__ = "events"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    date = Column(String)  # Using String for simplicity

    seat_pricing = relationship("EventSeatPricing", back_populates="event")


class Section(Base):
    __tablename__ = "sections"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    venue_id = Column(Integer, nullable=False)
    is_rowless = Column(Boolean, default=False)

    rows = relationship("Row", back_populates="section")


class Row(Base):
    __tablename__ = "rows"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    section_id = Column(Integer, ForeignKey("sections.id"))

    section = relationship("Section", back_populates="rows")
    seats = relationship("Seat", back_populates="row")


class Seat(Base):
    __tablename__ = "seats"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    row_id = Column(Integer, ForeignKey("rows.id"))
    number = Column(Integer)
    position_in_row = Column(Integer, nullable=False)

    row = relationship("Row", back_populates="seats")
    pricing = relationship("EventSeatPricing", back_populates="seat")


class PriceLevel(Base):
    __tablename__ = "price_levels"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    price = Column(Float, nullable=False)

    seat_pricing = relationship("EventSeatPricing", back_populates="price_level")


class SeatStatus(Base):
    __tablename__ = "seat_status"

    code = Column(String(1), primary_key=True)
    description = Column(String, nullable=False)
    is_available = Column(Boolean, nullable=False)


class EventSeatPricing(Base):
    __tablename__ = "event_seat_pricing"

    id = Column(Integer, primary_key=True, index=True)
    event_id = Column(Integer, ForeignKey("events.id"))
    seat_id = Column(Integer, ForeignKey("seats.id"))
    price_level_id = Column(Integer, ForeignKey("price_levels.id"))
    status_code = Column(String(1), ForeignKey("seat_status.code"))
    hold_comment = Column(String)
    note = Column(String)

    event = relationship("Event", back_populates="seat_pricing")
    seat = relationship("Seat", back_populates="pricing")
    price_level = relationship("PriceLevel", back_populates="seat_pricing")
    status = relationship("SeatStatus")

class RawEventData(Base):
    __tablename__ = "raw_event_data"
    id = Column(Integer, primary_key=True)
    payload = Column(Text)  # store raw JSON as string
    created_at = Column(DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "payload": json.loads(self.payload),
            "created_at": self.created_at.isoformat()
        }
