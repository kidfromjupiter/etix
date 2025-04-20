import json
from typing import List

import uvicorn
from fastapi import FastAPI, Depends, Request, HTTPException
from sqlalchemy.orm import Session

from backend import crud
from backend.models import Event, Section, Seat, RawEventData
from backend.schema import RawData, TicketDataIngest, AdjacentSeatsResponse, EventCreate
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


DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/1362758832635248760/_tQk6Urjk8qxZksEwHGmXeKdxJDvgMRdmAsVyjWLUsrS9b4-BriCPn2-75MS_lDWkIvD"

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
async def ingest_ticket_data(
        ticket_data: TicketDataIngest,
        db: Session = Depends(get_db)
):
    try:
        # Convert Pydantic model to dict and add section
        data_dict = ticket_data.dict()
        section_name = data_dict.pop('section')

        # Process the data
        data=  crud.ingest_ticket_data(db, data_dict, section_name, ticket_data.event_id)
        async with httpx.AsyncClient() as client:
            await client.post(DISCORD_WEBHOOK_URL, json={
                "content": f"🧾 Ingested raw event entries"
            })
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {"status": "ok"}


@app.get("/event/{event_id}", response_model=List[AdjacentSeatsResponse])
def get_adjacent_groups(
        event_id: int,
        min_seats: int = 2,
        db: Session = Depends(get_db)
):
    """
    Get dynamically calculated adjacent seat groups for an event.
    Default minimum group size is 2 seats.
    """
    adjacent_groups = crud.calculate_adjacent_seats(db, event_id, min_seats)

    if not adjacent_groups:
        raise HTTPException(
            status_code=404,
            detail=f"No adjacent seat groups found with {min_seats} or more seats"
        )

    return adjacent_groups

@app.post("/event")
def create_event(payload: EventCreate, db: Session = Depends(get_db)):
   event = Event(
       name=payload.name,
       date=str(payload.date),
   )
   db.add(event)
   db.commit()
   db.refresh(event)
   return {"status": "event added", "event_id": event.id}

if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)