import asyncio
import json
import time
import uuid
from typing import List

import uvicorn
from fastapi import FastAPI, Depends, Request, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import select, delete

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


last_reset_time = 0
remaining_requests = 5  # default
lock = asyncio.Lock()


async def send_to_discord( message):
    global last_reset_time, remaining_requests


    async with lock:
        now = time.time()
        if remaining_requests == 0 and now < last_reset_time:
            sleep_for = last_reset_time - now
            await asyncio.sleep(sleep_for)

        async with httpx.AsyncClient() as client:
            response = await client.post(DISCORD_WEBHOOK_URL, json={"content": message})

            # Parse rate limit headers
            remaining = response.headers.get("X-RateLimit-Remaining")
            reset = response.headers.get("X-RateLimit-Reset")
            retry_after = response.headers.get("Retry-After")

            if remaining is not None:
                remaining_requests = int(remaining)

            if reset is not None:
                last_reset_time = float(reset)

            if response.status_code == 429 and retry_after:
                await asyncio.sleep(float(retry_after))

            if response.status_code >= 400:
                print("Failed to send message:", response.text)
            
            if response.status_code == 200:
                print("Sent message to discord")
            else:
                print(response.text)



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
    
    # Get all current seats for this event
    current_seats = db.execute(
        select(Seat).where(Seat.event_id == payload.event_id)
    ).scalars().all()
    
    current_seat_identifiers = {seat.id for seat in current_seats}

    # New seat identifiers from payload
    incoming_seat_identifiers = set()

    new_alerts = []

    for row in payload.rows:
        for seat_data in row.seats:
            seat_id = f"{payload.event_id}_{payload.section}_{seat_data.seatIdentifier}"
            incoming_seat_identifiers.add(seat_id)
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

    # Delete seats that are missing
    seats_to_delete = current_seat_identifiers - incoming_seat_identifiers
    if seats_to_delete:
        db.execute(
            delete(Seat).where(Seat.id.in_(seats_to_delete), Seat.event_id == payload.event_id, Seat.section == payload.section)
        )

    db.commit()

    if len(new_alerts) <= 4:
        for alert in new_alerts:
            message = (
                f"🎟️ **New Seat Available!**\n"
                f"**Event:** {alert.get('eventUrl')}\n"
                f"**Section:** {alert.get('section')}\n"
                f"**Row:** {alert.get('row')}\n"
                f"**Seat:** {alert.get('seat')}\n"
                f"**Price:** ${alert.get('price')}"
            )
            asyncio.create_task(send_to_discord(message))
    else: 
        message = (
            f"**Event:** {event.url}\n"
            f"Found {len(new_alerts)} seats in section {payload.section}"
            )
        asyncio.create_task(send_to_discord(message))

    return {"message": f"{len(new_alerts)} new available seats ingested"}



if __name__ == "__main__":
    uvicorn.run("backend_main:app", host="127.0.0.1", port=4000, reload=False)
