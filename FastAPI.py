from fastapi import FastAPI, BackgroundTasks, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
from datetime import datetime
import httpx
import logging
import os
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, JSON, MetaData, Table
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from contextlib import contextmanager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("api")

# Database setup with SQLAlchemy
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./scrape_data.db")
engine = create_engine(DATABASE_URL)
metadata = MetaData()
Base = declarative_base()

class ScrapeData(Base):
    __tablename__ = "scrape_data"

    id = Column(Integer, primary_key=True, index=True)
    runner_id = Column(String, index=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
    url = Column(String)
    data = Column(JSON)
    status = Column(String)  # success or error
    error_message = Column(Text, nullable=True)

# Create tables
Base.metadata.create_all(bind=engine)

# Create session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

@contextmanager
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# FastAPI app
app = FastAPI(title="Scraper API",
              description="API for handling web scraping data and Discord notifications")

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Adjust in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Models
class ScrapeDataRequest(BaseModel):
    runner_id: str
    url: str
    data: Dict[str, Any]
    status: str = "success"
    error_message: Optional[str] = None
    timestamp: Optional[datetime] = None

class DiscordWebhook(BaseModel):
    webhook_url: Optional[str] = None  # Optional here, will use env var if not provided
    content: str
    embeds: Optional[List[Dict[str, Any]]] = None

# Discord webhook handling
async def send_discord_webhook(webhook_data: DiscordWebhook):
    """Send data to Discord webhook"""
    webhook_url = webhook_data.webhook_url or os.getenv("DISCORD_WEBHOOK_URL")

    if not webhook_url:
        logger.warning("No Discord webhook URL provided")
        return False

    async with httpx.AsyncClient() as client:
        try:
            webhook_payload = {
                "content": webhook_data.content
            }
            if webhook_data.embeds:
                webhook_payload["embeds"] = webhook_data.embeds

            response = await client.post(
                webhook_url,
                json=webhook_payload
            )
            response.raise_for_status()
            logger.info(f"Discord webhook sent successfully")
            return True
        except httpx.HTTPError as e:
            logger.error(f"Error sending Discord webhook: {str(e)}")
            return False

# Routes
@app.post("/api/scrape-data", status_code=201)
async def receive_scrape_data(
        scrape_data: ScrapeDataRequest,
        background_tasks: BackgroundTasks,
        db: Session = Depends(lambda: next(get_db()))
):
    """Endpoint for EventManager to submit scraped data"""
    try:
        # Prepare data for storage
        db_scrape_data = ScrapeData(
            runner_id=scrape_data.runner_id,
            url=scrape_data.url,
            data=scrape_data.data,
            status=scrape_data.status,
            error_message=scrape_data.error_message,
            timestamp=scrape_data.timestamp or datetime.utcnow()
        )

        # Store in database
        db.add(db_scrape_data)
        db.commit()
        db.refresh(db_scrape_data)

        logger.info(f"Stored scrape data for runner {scrape_data.runner_id} from {scrape_data.url}")

        return {"status": "success", "id": db_scrape_data.id}

    except Exception as e:
        logger.error(f"Error processing scrape data: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error processing data: {str(e)}")

@app.get("/api/scrape-data/{runner_id}", response_model=List[dict])
def get_runner_data(
        runner_id: str,
        limit: int = 10,
        db: Session = Depends(lambda: next(get_db()))
):
    """Retrieve scrape data for a specific runner"""
    data = db.query(ScrapeData).filter(ScrapeData.runner_id == runner_id).order_by(
        ScrapeData.timestamp.desc()
    ).limit(limit).all()

    results = []
    for item in data:
        results.append({
            "id": item.id,
            "runner_id": item.runner_id,
            "url": item.url,
            "data": item.data,
            "status": item.status,
            "error_message": item.error_message,
            "timestamp": item.timestamp
        })

    return results

@app.get("/api/health")
def health_check():
    """Health check endpoint"""
    return {"status": "ok", "timestamp": datetime.utcnow()}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("fastapi_backend:app", host="0.0.0.0", port=8000, reload=True)
