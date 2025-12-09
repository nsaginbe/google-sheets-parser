import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import OAuth2PasswordRequestForm

from app.auth import (authenticate_user, get_current_user, issue_token_pair,
                      verify_refresh_token)
from app.models import (AvailabilityRequest, AvailabilityResponse,
                        CalendarInfo, ConnectionCheckResponse,
                        LoadCalendarRequest, LoadCalendarResponse,
                        RefreshRequest, RoomAvailability, TokenPair)
from app.parser import Parser

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

parser: Optional[Parser] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global parser
    try:
        parser = Parser()
    except Exception as e:
        logger.error(f"Parser init failed: {e}")
        parser = None
    yield
    parser = None


app = FastAPI(title="Parser API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _require_parser():
    if parser is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Parser not initialized",
        )


@app.get("/health", tags=["Health"])
async def health_check():
    return {"status": "healthy", "parser_initialized": parser is not None}


@app.post("/auth/login", response_model=TokenPair, tags=["Auth"])
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    if not authenticate_user(form_data.username, form_data.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials"
        )
    return issue_token_pair(form_data.username)


@app.post("/auth/refresh", response_model=TokenPair, tags=["Auth"])
async def refresh_tokens(request: RefreshRequest):
    username = verify_refresh_token(request.refresh_token)
    return issue_token_pair(username)


@app.get("/connection/check", response_model=ConnectionCheckResponse)
async def check_connection_get(
    spreadsheet_id: Optional[str] = None, current_user: str = Depends(get_current_user)
):
    _require_parser()
    result = parser.check_connection(spreadsheet_id)
    return ConnectionCheckResponse(**result)


@app.post("/calendar/load", response_model=LoadCalendarResponse, tags=["Calendar"])
async def load_calendar(
    request: LoadCalendarRequest, current_user: str = Depends(get_current_user)
):
    _require_parser()

    spreadsheet_id = request.spreadsheet_id or os.getenv("SPREADSHEET_ID")
    sheet_name = request.sheet_name or os.getenv("SHEET_NAME")
    date_start_cell = request.date_start_cell or os.getenv("DATE_START_CELL")
    date_start = request.date_start or os.getenv("DATE_START")

    if not spreadsheet_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="spreadsheet_id is required",
        )

    parser.load_calendar(spreadsheet_id, sheet_name, date_start_cell, date_start)
    calendar_info = parser.get_calendar_info()
    return LoadCalendarResponse(
        success=True,
        message="Calendar loaded",
        calendar_info=CalendarInfo(**calendar_info) if calendar_info else None,
    )


@app.get("/calendar/info", response_model=CalendarInfo, tags=["Calendar"])
async def get_calendar_info(current_user: str = Depends(get_current_user)):
    _require_parser()
    if not parser.date_column_map:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Calendar not loaded",
        )
    return CalendarInfo(**parser.get_calendar_info())


@app.post("/rooms/available", response_model=AvailabilityResponse, tags=["Rooms"])
async def get_available_rooms(
    request: AvailabilityRequest, current_user: str = Depends(get_current_user)
):
    _require_parser()
    if not parser.sheet_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Calendar not loaded",
        )

    if request.check_out < request.check_in:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="check_out must be >= check_in",
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
        category_filter=request.category_filter or None,
    )


@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"error": "Internal server error", "detail": str(exc)},
    )
