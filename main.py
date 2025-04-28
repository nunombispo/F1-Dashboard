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

# List of session types to exclude (testing sessions)
EXCLUDED_SESSION_TYPES = ["Testing", "Pre-Season Testing", "Post-Season Testing"]

# Fetch data from OpenF1 API
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

# Format date string to a more readable format
def format_date(date_str: str) -> str:
    """Format date string to a more readable format"""
    if not date_str:
        return "N/A"
    try:
        date = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
        return date.strftime("%Y-%m-%d %H:%M:%S")
    except:
        return date_str

# Get all races for the current year
async def get_all_races() -> List[Dict]:
    """Get all races for the current year"""
    current_year = datetime.now().year
    try:
        # Get all meetings for the current year
        meetings = await fetch_data("meetings", {"year": current_year})
        
        # Filter out testing sessions and add round numbers
        race_meetings = []
        round_number = 1
        
        for meeting in meetings:
            # Skip if it's a testing session
            if any(test_type in meeting.get("meeting_name", "") for test_type in EXCLUDED_SESSION_TYPES):
                continue
            
            # Add round number
            meeting["round_number"] = round_number
            round_number += 1
            # Add 2 days to the date_start
            meeting["date_start"] = (datetime.fromisoformat(meeting["date_start"]) + timedelta(days=2)).isoformat()
            race_meetings.append(meeting)
        
        # Sort meetings by date
        race_meetings.sort(key=lambda x: x.get("date_start", ""))
        
        return race_meetings
    except Exception as e:
        logger.error(f"Error fetching races: {str(e)}")
        return []

# Get the latest session for a specific meeting
async def get_session_for_meeting(meeting_key: int) -> Optional[Dict]:
    """Get the latest session for a specific meeting"""
    try:
        # Get all sessions for the meeting
        sessions = await fetch_data("sessions", {"meeting_key": meeting_key})
        
        if not sessions:
            return None
        
        # Filter out testing sessions
        race_sessions = [s for s in sessions if not any(test_type in s.get("session_name", "") for test_type in EXCLUDED_SESSION_TYPES)]
        
        if not race_sessions:
            return None
        
        # Sort sessions by date and get the latest
        race_sessions.sort(key=lambda x: x.get("date_start", ""), reverse=True)
        latest_session = race_sessions[0]
        
        # Format dates
        if latest_session.get("date_start"):
            latest_session["date_start"] = format_date(latest_session["date_start"])
        if latest_session.get("date_end"):
            latest_session["date_end"] = format_date(latest_session["date_end"])
        
        # Get weather data for the session
        try:
            weather_data = await fetch_data("weather", {"session_key": latest_session["session_key"]})
            if weather_data:
                # Get the latest weather data
                weather_data.sort(key=lambda x: x.get("date", ""), reverse=True)
                latest_session["weather"] = weather_data[0]
        except Exception as e:
            logger.error(f"Error fetching weather data: {str(e)}")
            latest_session["weather"] = None
        
        return latest_session
    except Exception as e:
        logger.error(f"Error fetching session for meeting {meeting_key}: {str(e)}")
        return None

# Home route
@app.get("/", response_class=HTMLResponse)
async def home(request: Request, meeting_key: Optional[int] = None):
    """Render the home page with session data"""
    try:
        # Get all races for the current year
        races = await get_all_races()
        
        if not races:
            return templates.TemplateResponse(
                "index.html",
                {
                    "request": request,
                    "error": "No races found for the current year",
                    "session": None,
                    "races": []
                }
            )
        
        # If a meeting key is provided, get the session for that meeting
        if meeting_key:
            # Get session for specific meeting
            session = await get_session_for_meeting(meeting_key)
        else:
            # Get the latest race
            latest_race = races[-1]
            session = await get_session_for_meeting(latest_race["meeting_key"])
        
        # If no session is found, return an error
        if not session:
            return templates.TemplateResponse(
                "index.html",
                {
                    "request": request,
                    "error": "No sessions found",
                    "session": None,
                    "races": races
                }
            )
        
        # Add meeting official name to session data
        session["meeting_official_name"] = next((race["meeting_official_name"] for race in races if race["meeting_key"] == session["meeting_key"]), "Unknown")

        # Render the home page with the session data
        return templates.TemplateResponse(
            "index.html",
            {
                "request": request,
                "session": session,
                "error": None,
                "races": races
            }
        )
    except Exception as e:
        logger.error(f"Error in home route: {str(e)}")
        return templates.TemplateResponse(
            "index.html",
            {
                "request": request,
                "error": str(e),
                "session": None,
                "races": []
            }
        )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000) 