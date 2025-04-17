from fastapi import FastAPI, Depends
from sqlalchemy.orm import Session
from backend.models import Event, Section, Seat
from backend.schema import SeatCreate, EventCreate
from backend.db import SessionLocal, init_db
import httpx

app = FastAPI()
init_db()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/your_webhook_here"

async def send_to_discord(seat_data: dict):
    message = (
        f"🎟️ **New Seat Available!**\n"
        f"**Event:** {seat_data.get('eventUrl')}\n"
        f"**Section:** {seat_data.get('section')}\n"
        f"**Row:** {seat_data.get('row')}\n"
        f"**Seat:** {seat_data.get('seat')}\n"
        f"**Price:** ${seat_data.get('price')}"
    )
    async with httpx.AsyncClient() as client:
        await client.post(DISCORD_WEBHOOK_URL, json={"content": message})

@app.post("/ingest")
def ingest_seat(payload: SeatCreate, db: Session = Depends(get_db)):
    # 1. Get or create event by URL
    event = db.query(Event).filter_by(url=payload.eventUrl).first()
    if not event:
        return {"error": "Event must be created before adding seats."}

    # 2. Get or create section
    section = (
        db.query(Section)
        .filter_by(event_id=event.id, name=payload.section)
        .first()
    )
    if not section:
        section = Section(name=payload.section, event_id=event.id)
        db.add(section)
        db.commit()
        db.refresh(section)

    # 3. Create seat
    seat = Seat(
        number=payload.seat,
        row=payload.row,
        price=payload.price,
        info=payload.info,
        section_id=section.id,
    )
    db.add(seat)
    db.commit()
    db.refresh(seat)

    return {"status": "seat added", "seat_id": seat.id}
@app.post("/event")
def create_event(payload: EventCreate, db: Session = Depends(get_db)):
    event = Event(
        name=payload.name,
        url=payload.url,
        date=payload.date,
        venue=payload.venue,
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return {"status": "event added", "event_id": event.id}