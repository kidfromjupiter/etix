import json
from datetime import datetime

from sqlalchemy import Column, Integer, String, Boolean, Float, ForeignKey, Text, DateTime
from sqlalchemy.orm import relationship, declarative_base

Base = declarative_base()

class Event(Base):
    __tablename__ = "events"
    id = Column(String, primary_key=True)
    url = Column(String, nullable=False)
    time = Column(String, nullable=True)

class Seat(Base):
    __tablename__ = "seats"
    id = Column(String, primary_key=True)
    event_id = Column(String, ForeignKey("events.id"))
    section = Column(String)
    row = Column(String)
    seat = Column(String)
    is_available = Column(Boolean)
    price = Column(String)

    event = relationship("Event")

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
