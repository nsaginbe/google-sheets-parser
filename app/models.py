"""Pydantic models for request/response validation"""
from __future__ import annotations

from datetime import date, datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class RoomAvailability(BaseModel):
    """Available room information"""

    category: str
    room: str


class CalendarInfo(BaseModel):
    """Calendar information"""

    total_dates: int
    date_range: dict = Field(..., description="Date range with min_date and max_date")
    years: List[int]
    header_row: int
    data_start_row: int
    sample_dates: Optional[List[str]] = None


class AvailabilityRequest(BaseModel):
    """Request for checking room availability"""

    check_in: date = Field(..., description="Check-in date (inclusive)")
    check_out: date = Field(..., description="Check-out date (inclusive). Must be >= check_in")
    category_filter: str = Field("", description='Category filter (e.g., "Deluxe"). Empty string or "ALL" means search in all categories')


class AvailabilityResponse(BaseModel):
    """Response with available rooms"""

    available_rooms: List[RoomAvailability]
    count: int
    check_in: date
    check_out: date
    category_filter: Optional[str] = None


class RoomCheckRequest(BaseModel):
    """Request for checking specific room availability"""

    model_config = ConfigDict(populate_by_name=True)

    room_number: str = Field(..., description="Room number (e.g., 'A-103')")
    check_date: date = Field(..., description="Date to check", alias="date")


class RoomCheckResponse(BaseModel):
    """Response for room availability check"""

    model_config = ConfigDict(populate_by_name=True)

    room_number: str
    check_date: date = Field(..., alias="date")
    available: bool


class CategoriesRequest(BaseModel):
    """Request for getting available categories"""

    check_in: date = Field(..., description="Check-in date")
    check_out: date = Field(..., description="Check-out date")


class CategoriesResponse(BaseModel):
    """Response with available categories"""

    categories: List[str]
    check_in: date
    check_out: date


def _get_env_value(key: str) -> Optional[str]:
    """Get value from environment variable"""
    import os

    from dotenv import load_dotenv

    load_dotenv()
    return os.getenv(key)


# Get env values at module load time for Swagger display
_ENV_SPREADSHEET_ID = _get_env_value("SPREADSHEET_ID")
_ENV_SHEET_NAME = _get_env_value("SHEET_NAME")
_ENV_DATE_START_CELL = _get_env_value("DATE_START_CELL")
_ENV_DATE_START = _get_env_value("DATE_START")


class LoadCalendarRequest(BaseModel):
    """Request for loading calendar"""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "spreadsheet_id": _ENV_SPREADSHEET_ID or "your_spreadsheet_id",
                "sheet_name": _ENV_SHEET_NAME,
                "date_start_cell": _ENV_DATE_START_CELL or "C7",
                "date_start": _ENV_DATE_START or "24.11.2025",
            }
        }
    )

    spreadsheet_id: Optional[str] = Field(
        default=_ENV_SPREADSHEET_ID,
        description=f"Google Spreadsheet ID. Default: {_ENV_SPREADSHEET_ID or '(from SPREADSHEET_ID env)'}",
    )
    sheet_name: Optional[str] = Field(
        default=_ENV_SHEET_NAME,
        description=f"Sheet name. Default: {_ENV_SHEET_NAME or '(from SHEET_NAME env or first sheet)'}",
    )
    date_start_cell: Optional[str] = Field(
        default=_ENV_DATE_START_CELL,
        description=f"Start cell for dates (e.g., 'C7'). Default: {_ENV_DATE_START_CELL or '(from DATE_START_CELL env or auto-detects)'}",
    )
    date_start: Optional[str] = Field(
        default=_ENV_DATE_START,
        description=f"Start date (e.g., '24.11.2025'). Default: {_ENV_DATE_START or '(from DATE_START env or reads from cell)'}",
    )


class LoadCalendarResponse(BaseModel):
    """Response for loading calendar"""

    success: bool
    message: str
    calendar_info: Optional[CalendarInfo] = None


class ErrorResponse(BaseModel):
    """Error response"""

    error: str
    detail: Optional[str] = None


class ConnectionCheckRequest(BaseModel):
    """Request for checking Google Sheets connection"""

    spreadsheet_id: Optional[str] = Field(
        None,
        description="Optional spreadsheet ID to test access. If not provided, only checks authentication.",
    )


class ConnectionCheckResponse(BaseModel):
    """Response for connection check"""

    connected: bool
    authenticated: bool
    message: str
    spreadsheet_accessible: Optional[bool] = None
    spreadsheet_title: Optional[str] = None
    error: Optional[str] = None
