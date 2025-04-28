from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from fastapi.requests import Request
import httpx
from datetime import datetime, timedelta
import logging
from typing import List, Dict, Optional

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="F1 Dashboard")

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# OpenF1 API base URL
OPENF1_BASE_URL = "https://api.openf1.org/v1"

async def fetch_data(endpoint: str, params: Optional[Dict] = None) -> List[Dict]:
    """Fetch data from OpenF1 API"""
    url = f"{OPENF1_BASE_URL}/{endpoint}"
    logger.info(f"Fetching data from: {url}")
    logger.info(f"With params: {params}")
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            logger.info(f"Received {len(data) if isinstance(data, list) else 1} items from {endpoint}")
            return data
        except httpx.HTTPError as e:
            logger.error(f"HTTP error fetching {endpoint}: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Error fetching data from OpenF1 API: {str(e)}")
        except Exception as e:
            logger.error(f"Unexpected error fetching {endpoint}: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")

def format_date(date_str: str) -> str:
    """Format date string to a more readable format"""
    if not date_str:
        return "N/A"
    try:
        date = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
        return date.strftime("%Y-%m-%d %H:%M:%S")
    except:
        return date_str

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """Render the home page with latest session data"""
    try:
        # Get sessions from the last 30 days
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=30)
        
        # Format dates for API
        start_str = start_date.strftime("%Y-%m-%d")
        end_str = end_date.strftime("%Y-%m-%d")
        
        logger.info(f"Fetching sessions between {start_str} and {end_str}")
        
        # Get latest session
        sessions = await fetch_data("sessions", {
            "date_start>": start_str,
            "date_end<": end_str
        })
        
        if not sessions:
            logger.warning("No sessions found in the last 30 days")
            return templates.TemplateResponse(
                "index.html",
                {
                    "request": request,
                    "error": "No sessions found in the last 30 days",
                    "session": None
                }
            )
        
        # Sort sessions by date and get the latest
        sessions.sort(key=lambda x: x.get("date_start", ""), reverse=True)
        latest_session = sessions[0]
        
        # Format dates in the session data
        if latest_session.get("date_start"):
            latest_session["date_start"] = format_date(latest_session["date_start"])
        if latest_session.get("date_end"):
            latest_session["date_end"] = format_date(latest_session["date_end"])
        
        logger.info(f"Found latest session: {latest_session.get('session_name')} ({latest_session.get('date_start')})")
        
        return templates.TemplateResponse(
            "index.html",
            {
                "request": request,
                "session": latest_session,
                "error": None
            }
        )
    except Exception as e:
        logger.error(f"Error in home route: {str(e)}")
        return templates.TemplateResponse(
            "index.html",
            {
                "request": request,
                "error": str(e),
                "session": None
            }
        )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000) 