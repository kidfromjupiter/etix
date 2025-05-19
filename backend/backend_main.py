import asyncio
from contextlib import asynccontextmanager
import os
import time
import uuid
import re
import uvicorn
from fastapi import FastAPI, Depends, Request, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import select, delete

#from backend import crud
from backend.utils.models import Event, Seat, RawEventData
from backend.utils.schema import SeatingPayload, EventCreateRequest, EventResponse
from backend.utils.db import SessionLocal, init_db
import httpx
from os import getenv
from utils.logger import setup_logger

from dotenv import load_dotenv

load_dotenv(override=True)

# creating logfile if isn't already there
log_path = os.path.join("logs", "fastapi.log")
if not os.path.exists(log_path):
    open(log_path, "w").close()

logger = setup_logger("FASTAPI", logfile='./logs/fastapi.log')
logger.propagate = False

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


DISCORD_WEBHOOK_URL = getenv("DISCORD_WEBHOOK_URL")
DEBUG = True if getenv("DEBUG", "True") == "True" else False
BUFFER_INTERVAL = 5 # in seconds
events_db = {}
seats_db = {}


last_reset_time = 0
buffer = []
buffer_lock = asyncio.Lock()
last_reset_time = 0
remaining_requests = 5
lock = asyncio.Lock()

logger.info(f"Discord webhook url: {DISCORD_WEBHOOK_URL}")
logger.info(f"Debug enabled: {DEBUG}")

async def flush_buffer():
    global buffer
    while True:
        await asyncio.sleep(BUFFER_INTERVAL)
        async with buffer_lock:
            if buffer:
                combined_message = "\n\n".join(buffer)
                buffer = []
                logger.info(f"Sending message: \n{combined_message}")
                if not DEBUG:
                    asyncio.create_task(send_to_discord(combined_message))
                else:
                    print("Buffered Message:\n", combined_message)

async def add_to_msg_buffer(message):
    async with buffer_lock:
        buffer.append(message)


async def send_to_discord( message):
    global last_reset_time, remaining_requests

    try:
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
                    logger.warning(f"Rate limited for {retry_after}")
                    await asyncio.sleep(float(retry_after))

                if response.status_code >= 400:
                    logger.error("Failed to send message:", response.text)

                if response.status_code == 200:
                    logger.info("Sent message to discord")
                else:
                    logger.warning(f"Got unhandled response from discord: {response.text}")
    except Exception as e:
        logger.error(f"Got an error in send_to_discord: {e[:60]}...")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    flush_task = asyncio.create_task(flush_buffer())

    yield  # Let the app run

    # Shutdown
    flush_task.cancel()
    try:
        await flush_task
    except asyncio.CancelledError:
        pass

app = FastAPI(lifespan=lifespan)
init_db()

@app.post("/create-event", response_model=EventResponse)
def create_event(data: EventCreateRequest, db: Session = Depends(get_db)):
    match = re.search(r'/([\d]+)/', data.url)
    if not match:
        raise HTTPException(status_code=422, detail="No event ID found in URL")

    event_id = match.group(1)

    # Try to get existing event
    event = db.query(Event).filter_by(id=event_id).first()

    if not event:
        event = Event(id=event_id, url=data.url, time=data.time)
        db.add(event)
        db.commit()
        db.refresh(event)

    logger.info(f"Created event with id:{event.id} for {event.url}") 

    return {"event_id": event.id, "url": event.url}


@app.post("/ingest")
async def ingest_seating(payload: SeatingPayload, db: Session = Depends(get_db)):


    event = db.query(Event).filter(Event.id == payload.event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    
    logger.info(f"Ingested seating info for {event.id} in section {payload.section}") 
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
                    "eventTime": event.time,
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
        if len(new_alerts) != 0:
            logger.info(f"Got {len(new_alerts)} new alerts for event: {event.id} for section {payload.section}")
        for alert in new_alerts:
            message = (
                f"🎟️ **New Seat Available!**\n"
                f"**Event:** {alert.get('eventUrl')}\n"
                f"**Time:** {alert.get('eventTime')}\n"
                f"**Section:** {alert.get('section')}\n"
                f"**Row:** {alert.get('row')}\n"
                f"**Seat:** {alert.get('seat')}\n"
                f"**Price:** ${alert.get('price')}"
            )
            asyncio.create_task(add_to_msg_buffer(message))
    else: 
        logger.info(f"Got more than 4 new alerts for event: {event.id} for section {payload.section}")
        message = (
            f"**Event:** {event.url}\n"
            f"**Time:** {event.time}\n"
            f"Found {len(new_alerts)} seats in section {payload.section}"
            )
        asyncio.create_task(add_to_msg_buffer(message))

    return {"message": f"{len(new_alerts)} new available seats ingested"}



if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.backend_main:app", host="127.0.0.1", port=4000, reload=False)
