from sqlalchemy import Column, Integer, String, Float, ForeignKey, DateTime
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()

class Event(Base):
    __tablename__ = "events"
    id = Column(Integer, primary_key=True)
    name = Column(String)
    url = Column(String, unique=True)
    date = Column(DateTime)
    venue = Column(String)

    sections = relationship("Section", back_populates="event")


class Section(Base):
    __tablename__ = "sections"
    id = Column(Integer, primary_key=True)
    name = Column(String)
    event_id = Column(Integer, ForeignKey("events.id"))

    event = relationship("Event", back_populates="sections")
    seats = relationship("Seat", back_populates="section")


class Seat(Base):
    __tablename__ = "seats"
    id = Column(Integer, primary_key=True)
    number = Column(String)
    row = Column(String)
    price = Column(Float)
    info = Column(String)
    section_id = Column(Integer, ForeignKey("sections.id"))

    section = relationship("Section", back_populates="seats")
