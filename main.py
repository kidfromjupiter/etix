import json
import uuid
from typing import List

import uvicorn
from fastapi import FastAPI, Depends, Request, HTTPException
from sqlalchemy.orm import Session

#from backend import crud
from backend.models import Event, Seat, RawEventData
from backend.schema import SeatingPayload, EventCreateRequest, EventResponse
from backend.db import SessionLocal, init_db
import httpx
from os import getenv

from dotenv import load_dotenv

load_dotenv()

app = FastAPI()
init_db()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


DISCORD_WEBHOOK_URL = getenv("DISCORD_WEBHOOK_URL")
events_db = {}
seats_db = {}

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

    print("Sent data to discord")



@app.post("/create-event", response_model=EventResponse)
def create_event(data: EventCreateRequest, db: Session = Depends(get_db)):
    event_id = str(uuid.uuid4())
    event = Event(id=event_id, url=data.url)
    db.add(event)
    db.commit()
    db.refresh(event)
    return {"event_id": event_id, "url": data.url}


@app.post("/ingest")
async def ingest_seating(payload: SeatingPayload, db: Session = Depends(get_db)):

    event = db.query(Event).filter(Event.id == payload.event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    new_alerts = []

    for row in payload.rows:
        for seat_data in row.seats:
            seat_id = f"{payload.event_id}_{seat_data.seatIdentifier}"
            seat = db.query(Seat).filter(Seat.id == seat_id).first()

            is_newly_available = (
                    seat_data.isAvailable and
                    (not seat or not seat.is_available)
            )

            if seat:
                seat.row = seat_data.row
                seat.seat = seat_data.seat
                seat.section = payload.section
                seat.is_available = seat_data.isAvailable
                seat.price = seat_data.priceNum
            else:
                seat = Seat(
                    id=seat_id,
                    event_id=payload.event_id,
                    section=payload.section,
                    row=seat_data.row,
                    seat=seat_data.seat,
                    is_available=seat_data.isAvailable,
                    price=seat_data.priceNum,
                )
                db.add(seat)

            if is_newly_available:
                new_alerts.append({
                    "eventUrl": event.url,
                    "section": payload.section,
                    "row": seat_data.row,
                    "seat": seat_data.seat,
                    "price": seat_data.priceNum
                })

    db.commit()
    db.close()

    for alert in new_alerts:
        await send_to_discord(alert)

    return {"message": f"{len(new_alerts)} new available seats ingested"}



if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=4000, reload=True)
