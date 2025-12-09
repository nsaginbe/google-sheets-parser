from __future__ import annotations

import os
from datetime import date
from typing import List, Optional

from dotenv import load_dotenv
from pydantic import BaseModel, Field

load_dotenv()


class RoomAvailability(BaseModel):
    category: str
    room: str


class CalendarInfo(BaseModel):
    total_dates: int
    date_range: dict = Field(...)
    years: List[int]
    header_row: int
    data_start_row: int
    sample_dates: Optional[List[str]] = None


class AvailabilityRequest(BaseModel):
    check_in: date = Field(...)
    check_out: date = Field(...)
    category_filter: str = Field("ALL")


class AvailabilityResponse(BaseModel):
    available_rooms: List[RoomAvailability]
    count: int
    check_in: date
    check_out: date
    category_filter: Optional[str] = None


class LoadCalendarRequest(BaseModel):
    spreadsheet_id: Optional[str] = Field(default=os.getenv("SPREADSHEET_ID"))
    sheet_name: Optional[str] = Field(default=os.getenv("SHEET_NAME"))
    date_start_cell: Optional[str] = Field(default=os.getenv("DATE_START_CELL"))
    date_start: Optional[str] = Field(default=os.getenv("DATE_START"))


class LoadCalendarResponse(BaseModel):
    success: bool
    message: str
    calendar_info: Optional[CalendarInfo] = None


class ErrorResponse(BaseModel):
    error: str
    detail: Optional[str] = None


class ConnectionCheckRequest(BaseModel):
    spreadsheet_id: Optional[str] = Field(default=os.getenv("SPREADSHEET_ID"))


class ConnectionCheckResponse(BaseModel):
    connected: bool
    authenticated: bool
    message: str
    spreadsheet_accessible: Optional[bool] = None
    spreadsheet_title: Optional[str] = None
    error: Optional[str] = None


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


class LoginRequest(BaseModel):
    username: str
    password: str
