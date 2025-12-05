import logging
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.models import (AvailabilityRequest, AvailabilityResponse,
                        CalendarInfo, CategoriesRequest, CategoriesResponse,
                        ConnectionCheckRequest, ConnectionCheckResponse,
                        ErrorResponse, LoadCalendarRequest,
                        LoadCalendarResponse, RoomAvailability,
                        RoomCheckRequest, RoomCheckResponse)
from app.parser import HotelBookingParser

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Global parser instance
parser: HotelBookingParser = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup/shutdown"""
    global parser
    # Startup
    try:
        parser = HotelBookingParser()
        logger.info("Parser initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize parser: {e}")
        parser = None
    yield
    # Shutdown
    parser = None
    logger.info("Parser shutdown")


app = FastAPI(
    title="Hotel Booking Parser API",
    description="API for parsing and querying hotel booking calendars from Google Sheets",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", tags=["Health"])
async def health_check():
    return {"status": "healthy", "parser_initialized": parser is not None}


@app.get("/connection/check", response_model=ConnectionCheckResponse)
async def check_connection_get(spreadsheet_id: Optional[str] = None):
    """
    Check connection to Google Sheets API (GET method)

    - Tests authentication with Google Sheets API
    - Optionally tests access to a specific spreadsheet if spreadsheet_id query parameter is provided

    **Query parameters:**
    - `spreadsheet_id` (optional): Spreadsheet ID to test access
    """
    if parser is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Parser not initialized. Check authentication credentials.",
        )

    try:
        result = parser.check_connection(spreadsheet_id)
        return ConnectionCheckResponse(**result)
    except Exception as e:
        logger.error(f"Error checking connection: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error checking connection: {str(e)}",
        )


@app.post("/calendar/load", response_model=LoadCalendarResponse, tags=["Calendar"])
async def load_calendar(request: LoadCalendarRequest):
    """
    Load calendar from Google Sheets

    All parameters are optional and will use values from environment variables if not provided:
    - **spreadsheet_id**: Google Spreadsheet ID (from URL). Default: SPREADSHEET_ID from env
    - **sheet_name**: Sheet name. Default: SHEET_NAME from env or first sheet
    - **date_start_cell**: Start cell for dates (e.g., 'C7'). Default: DATE_START_CELL from env
    - **date_start**: Start date (e.g., '24.11.2025'). Default: DATE_START from env
    """
    if parser is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Parser not initialized. Check authentication credentials.",
        )

    try:
        import os

        from dotenv import load_dotenv

        load_dotenv()

        # Get values from request or fallback to env
        spreadsheet_id = request.spreadsheet_id or os.getenv("SPREADSHEET_ID")
        sheet_name = request.sheet_name or os.getenv("SHEET_NAME")
        date_start_cell = request.date_start_cell or os.getenv("DATE_START_CELL")
        date_start = request.date_start or os.getenv("DATE_START")

        if not spreadsheet_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="spreadsheet_id is required. Provide it in request body or set SPREADSHEET_ID in environment variables.",
            )

        success = parser.load_calendar(
            spreadsheet_id, sheet_name, date_start_cell, date_start
        )

        if success:
            calendar_info = parser.get_calendar_info()
            return LoadCalendarResponse(
                success=True,
                message="Calendar loaded successfully",
                calendar_info=CalendarInfo(**calendar_info) if calendar_info else None,
            )
        else:
            return LoadCalendarResponse(
                success=False,
                message="Failed to load calendar. Check spreadsheet ID and permissions.",
            )
    except Exception as e:
        logger.error(f"Error loading calendar: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error loading calendar: {str(e)}",
        )


@app.get("/calendar/info", response_model=CalendarInfo, tags=["Calendar"])
async def get_calendar_info():
    """Get information about the loaded calendar"""
    if parser is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Parser not initialized",
        )

    if not hasattr(parser, "date_column_map") or not parser.date_column_map:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Calendar not loaded. Call /calendar/load first.",
        )

    try:
        info = parser.get_calendar_info()
        return CalendarInfo(**info)
    except Exception as e:
        logger.error(f"Error getting calendar info: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error getting calendar info: {str(e)}",
        )


@app.post("/rooms/available", response_model=AvailabilityResponse, tags=["Rooms"])
async def get_available_rooms(request: AvailabilityRequest):
    """
    Get available rooms for a date range
    
    - **check_in**: Check-in date (inclusive)
    - **check_out**: Check-out date (inclusive)
    - **category_filter**: Category filter (e.g., "Deluxe"). Empty string means search in all categories
    """
    if parser is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Parser not initialized",
        )

    if not hasattr(parser, "sheet_data") or parser.sheet_data is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Calendar not loaded. Call /calendar/load first.",
        )

    try:
        from datetime import datetime

        # Validate date range
        if request.check_out < request.check_in:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="check_out must be greater than or equal to check_in"
            )

        check_in_dt = datetime.combine(request.check_in, datetime.min.time())
        check_out_dt = datetime.combine(request.check_out, datetime.min.time())

        available = parser.get_available_rooms(
            check_in_dt, check_out_dt, request.category_filter
        )

        rooms = [RoomAvailability(**room) for room in available]

        return AvailabilityResponse(
            available_rooms=rooms,
            count=len(rooms),
            check_in=request.check_in,
            check_out=request.check_out,
            category_filter=request.category_filter if request.category_filter else None,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Error getting available rooms: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error getting available rooms: {str(e)}",
        )


@app.post("/rooms/check", response_model=RoomCheckResponse, tags=["Rooms"])
async def check_room_availability(request: RoomCheckRequest):
    """
    Check if a specific room is available on a specific date

    - **room_number**: Room number (e.g., "A-103")
    - **date**: Date to check
    """
    if parser is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Parser not initialized",
        )

    if not hasattr(parser, "sheet_data") or parser.sheet_data is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Calendar not loaded. Call /calendar/load first.",
        )

    try:
        from datetime import datetime

        date_dt = datetime.combine(request.check_date, datetime.min.time())

        is_available = parser.check_room_availability(request.room_number, date_dt)

        return RoomCheckResponse(
            room_number=request.room_number,
            check_date=request.check_date,
            available=is_available,
        )
    except Exception as e:
        logger.error(f"Error checking room availability: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error checking room availability: {str(e)}",
        )


@app.post(
    "/categories/available", response_model=CategoriesResponse, tags=["Categories"]
)
async def get_available_categories(request: CategoriesRequest):
    """
    Get list of categories that have at least one available room

    - **check_in**: Check-in date
    - **check_out**: Check-out date
    """
    if parser is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Parser not initialized",
        )

    if not hasattr(parser, "sheet_data") or parser.sheet_data is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Calendar not loaded. Call /calendar/load first.",
        )

    try:
        from datetime import datetime

        check_in_dt = datetime.combine(request.check_in, datetime.min.time())
        check_out_dt = datetime.combine(request.check_out, datetime.min.time())

        categories = parser.get_available_categories(check_in_dt, check_out_dt)

        return CategoriesResponse(
            categories=categories,
            check_in=request.check_in,
            check_out=request.check_out,
        )
    except Exception as e:
        logger.error(f"Error getting available categories: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error getting available categories: {str(e)}",
        )


@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """Global exception handler"""
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"error": "Internal server error", "detail": str(exc)},
    )
