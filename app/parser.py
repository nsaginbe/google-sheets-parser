"""Refactored hotel booking parser"""
import logging
import os
import re
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

from dotenv import load_dotenv
from google.oauth2 import service_account
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# Load environment variables from .env file
load_dotenv()

logger = logging.getLogger(__name__)


class HotelBookingParser:
    """Parser for hotel booking calendars from Google Sheets"""

    def __init__(self):
        """Initialize Google Sheets API client"""
        self.service = None
        self._authenticate()
        self.date_column_map: Dict[datetime.date, int] = {}
        self.header_row_index: Optional[int] = None
        self.data_start_row: Optional[int] = None
        self.merged_cells_map: Dict[Tuple[int, int], Tuple[int, int, int, int]] = {}
        self.sheet_data: Optional[List[List]] = None

    def _authenticate(self):
        """Authenticate with Google Sheets API"""
        try:
            # Option 1: Service Account (recommended for server-side)
            credentials_path = os.getenv("GOOGLE_CREDENTIALS_PATH")
            if credentials_path and os.path.exists(credentials_path):
                credentials = service_account.Credentials.from_service_account_file(
                    credentials_path,
                    scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"],
                )
                self.service = build("sheets", "v4", credentials=credentials)
                logger.info("Authenticated using service account")
                return

            raise ValueError(
                "No valid credentials found. Set GOOGLE_CREDENTIALS_PATH or GOOGLE_CREDENTIALS_JSON in .env"
            )

        except Exception as e:
            logger.error(f"Authentication error: {e}")
            raise

    def check_connection(self, spreadsheet_id: Optional[str] = None) -> Dict:
        result = {
            "connected": False,
            "authenticated": False,
            "message": "",
            "spreadsheet_accessible": None,
            "spreadsheet_title": None,
            "error": None,
        }

        try:
            # Check if service is initialized
            if self.service is None:
                result["message"] = "Service not initialized"
                result["error"] = "Google Sheets service not available"
                return result

            result["authenticated"] = True
            result["connected"] = True
            result["message"] = "Successfully authenticated with Google Sheets API"

            # If spreadsheet_id is provided, test access to it
            if spreadsheet_id:
                try:
                    spreadsheet = (
                        self.service.spreadsheets()
                        .get(spreadsheetId=spreadsheet_id)
                        .execute()
                    )

                    result["spreadsheet_accessible"] = True
                    result["spreadsheet_title"] = spreadsheet.get("properties", {}).get(
                        "title", "Unknown"
                    )
                    result[
                        "message"
                    ] = f"Successfully connected. Access to spreadsheet '{result['spreadsheet_title']}' confirmed."

                except HttpError as e:
                    result["spreadsheet_accessible"] = False
                    error_reason = (
                        e.error_details[0].get("reason", "Unknown error")
                        if e.error_details
                        else str(e)
                    )

                    if e.resp.status == 404:
                        result[
                            "error"
                        ] = f"Spreadsheet not found (ID: {spreadsheet_id})"
                        result[
                            "message"
                        ] = "Authenticated, but spreadsheet not found. Check the spreadsheet ID."
                    elif e.resp.status == 403:
                        result["error"] = "Permission denied"
                        result[
                            "message"
                        ] = "Authenticated, but no access to this spreadsheet. Make sure the service account has access."
                    else:
                        result["error"] = f"HTTP {e.resp.status}: {error_reason}"
                        result[
                            "message"
                        ] = f"Authenticated, but error accessing spreadsheet: {error_reason}"

                except Exception as e:
                    result["spreadsheet_accessible"] = False
                    result["error"] = str(e)
                    result[
                        "message"
                    ] = f"Authenticated, but error accessing spreadsheet: {str(e)}"

            return result

        except Exception as e:
            result["error"] = str(e)
            result["message"] = f"Connection check failed: {str(e)}"
            logger.error(f"Connection check error: {e}")
            return result

    def _parse_month_name(self, text: str) -> Optional[int]:
        """Parse month name to month number (1-12)"""
        if not text or not isinstance(text, str):
            return None

        text = text.strip().lower()

        # Russian month names
        months_ru = {
            "январь": 1,
            "янв": 1,
            "февраль": 2,
            "фев": 2,
            "март": 3,
            "мар": 3,
            "апрель": 4,
            "апр": 4,
            "май": 5,
            "июнь": 6,
            "июн": 6,
            "июль": 7,
            "июл": 7,
            "август": 8,
            "авг": 8,
            "сентябрь": 9,
            "сен": 9,
            "октябрь": 10,
            "окт": 10,
            "ноябрь": 11,
            "ноя": 11,
            "декабрь": 12,
            "дек": 12,
        }

        # English month names
        months_en = {
            "january": 1,
            "jan": 1,
            "february": 2,
            "feb": 2,
            "march": 3,
            "mar": 3,
            "april": 4,
            "apr": 4,
            "may": 5,
            "june": 6,
            "jun": 6,
            "july": 7,
            "jul": 7,
            "august": 8,
            "aug": 8,
            "september": 9,
            "sep": 9,
            "october": 10,
            "oct": 10,
            "november": 11,
            "nov": 11,
            "december": 12,
            "dec": 12,
        }

        if text in months_ru:
            return months_ru[text]
        if text in months_en:
            return months_en[text]

        return None

    def _parse_date(
        self,
        date_str: str,
        default_month: Optional[int] = None,
        default_year: Optional[int] = None,
    ) -> Optional[datetime]:
        """Parse date from various formats"""
        if not date_str or not isinstance(date_str, str):
            return None

        date_str = date_str.strip()

        if default_year is None:
            default_year = datetime.now().year

        formats = [
            "%d.%m.%Y",
            "%d/%m/%Y",
            "%Y-%m-%d",
            "%d.%m",
            "%d/%m",
        ]

        for fmt in formats:
            try:
                parsed = datetime.strptime(date_str, fmt)
                if default_year and parsed.year == 1900:
                    parsed = parsed.replace(year=default_year)
                return parsed
            except ValueError:
                continue

        numbers = re.findall(r"\d+", date_str)
        if numbers:
            try:
                day = int(numbers[0])
                if 1 <= day <= 31:
                    month = default_month if default_month else datetime.now().month
                    return datetime(default_year, month, day)
            except ValueError:
                pass

        return None

    def _col_index_to_letter(self, col_idx: int) -> str:
        """Convert 0-based column index to Excel column letter"""
        result = ""
        col_idx += 1
        while col_idx > 0:
            col_idx -= 1
            result = chr(65 + (col_idx % 26)) + result
            col_idx //= 26
        return result

    def _cell_to_indices(self, cell_ref: str) -> Tuple[int, int]:
        """
        Convert Excel cell reference (e.g., 'C7') to 0-based row and column indices
        Returns: (row_index, col_index)
        """
        # Parse cell reference like 'C7' or 'AA10'
        import re

        match = re.match(r"^([A-Z]+)(\d+)$", cell_ref.upper())
        if not match:
            raise ValueError(f"Invalid cell reference: {cell_ref}")

        col_letters = match.group(1)
        row_number = int(match.group(2))

        # Convert column letters to index (A=0, B=1, ..., Z=25, AA=26, ...)
        col_idx = 0
        for char in col_letters:
            col_idx = col_idx * 26 + (ord(char) - ord("A") + 1)
        col_idx -= 1  # Convert to 0-based

        # Convert row number to 0-based index
        row_idx = row_number - 1

        return row_idx, col_idx

    def _parse_dates_from_start_cell(
        self, data: List[List], start_cell: str, start_date_str: Optional[str] = None
    ) -> Tuple[Optional[int], Dict[datetime.date, int]]:
        """
        Parse dates starting from a specified cell, going right sequentially.

        Args:
            data: Sheet data
            start_cell: Excel cell reference (e.g., 'C7')
            start_date_str: Optional start date string (e.g., '24.11.2025')
                          If not provided, will try to read from the cell itself

        Returns:
            (header_row_index, date_column_map)
        """
        try:
            # Parse cell reference to indices
            start_row_idx, start_col_idx = self._cell_to_indices(start_cell)

            if start_row_idx >= len(data):
                logger.error(f"Start row {start_row_idx + 1} is out of bounds")
                return None, {}

            # Get start date
            start_date = None

            # Option 1: Use provided start_date_str
            if start_date_str:
                start_date = self._parse_date(start_date_str)
                if not start_date:
                    logger.warning(
                        f"Could not parse start date from env: {start_date_str}"
                    )

            # Option 2: Try to read from the cell itself
            if not start_date:
                if start_row_idx < len(data) and start_col_idx < len(
                    data[start_row_idx]
                ):
                    cell_value = data[start_row_idx][start_col_idx]
                    if cell_value:
                        cell_str = str(cell_value).strip()
                        start_date = self._parse_date(cell_str)
                        if start_date:
                            logger.info(
                                f"Parsed start date from cell {start_cell}: {start_date.date()}"
                            )

            if not start_date:
                logger.error(
                    f"Could not determine start date from cell {start_cell} or env. Please provide DATE_START in env or ensure the cell contains a date."
                )
                return None, {}

            # Build date map going right from start cell
            date_map = {}
            current_date = start_date.date()
            col_idx = start_col_idx

            logger.info(
                f"Starting date parsing from cell {start_cell} with date {current_date}"
            )

            # Go right and create sequential dates until we hit an empty cell
            # Stop when we encounter an empty cell (no more dates)
            while True:
                # Check if row exists and column is within bounds
                if start_row_idx >= len(data):
                    break

                row = data[start_row_idx]
                if col_idx >= len(row):
                    # Column is out of bounds - treat as empty, stop
                    break

                # Get cell value
                cell_value = row[col_idx]
                cell_str = str(cell_value).strip() if cell_value else ""

                # If cell is empty, stop parsing
                if not cell_str:
                    logger.info(f"Stopped at empty cell (column {col_idx + 1})")
                    break

                # Skip day abbreviations (пн, вт, etc.)
                day_abbrevs = [
                    "пн",
                    "вт",
                    "ср",
                    "чт",
                    "пт",
                    "сб",
                    "вс",
                    "mon",
                    "tue",
                    "wed",
                    "thu",
                    "fri",
                    "sat",
                    "sun",
                ]
                if cell_str.lower() in day_abbrevs:
                    # Skip this column but continue
                    col_idx += 1
                    continue

                # Map the date to this column
                date_map[current_date] = col_idx

                # Move to next day and next column
                current_date += timedelta(days=1)
                col_idx += 1

            if date_map:
                logger.info(
                    f"Successfully parsed {len(date_map)} dates starting from {start_cell}"
                )
                return start_row_idx, date_map

            return None, {}

        except Exception as e:
            logger.error(f"Error parsing dates from start cell {start_cell}: {e}")
            return None, {}

    def _find_header_row(
        self, data: List[List]
    ) -> Tuple[Optional[int], Dict[datetime.date, int]]:
        """Find date headers and map dates to column indices"""
        date_map = {}
        current_year = datetime.now().year

        month_row_idx = None
        day_row_idx = None

        # Find row with months
        for row_idx in range(min(15, len(data))):
            row = data[row_idx]
            if len(row) < 3:
                continue

            month_count = 0
            for col_idx in range(2, min(len(row), 100)):
                cell_value = str(row[col_idx]).strip() if col_idx < len(row) else ""
                if self._parse_month_name(cell_value):
                    month_count += 1

            if month_count > 0:
                month_row_idx = row_idx
                if row_idx + 2 < len(data):
                    check_row = data[row_idx + 2]
                    day_numbers = 0
                    for check_col in range(2, min(len(check_row), 50)):
                        check_cell = (
                            str(check_row[check_col]).strip()
                            if check_col < len(check_row)
                            else ""
                        )
                        numbers = re.findall(r"\d+", check_cell)
                        if numbers:
                            day = int(numbers[0])
                            if 1 <= day <= 31:
                                day_numbers += 1

                    if day_numbers >= 5:
                        day_row_idx = row_idx + 2
                    elif row_idx + 1 < len(data):
                        day_row_idx = row_idx + 1
                elif row_idx + 1 < len(data):
                    day_row_idx = row_idx + 1
                break

        # If month row not found, search for day row directly
        if day_row_idx is None:
            for row_idx in range(min(20, len(data))):
                row = data[row_idx]
                if len(row) < 3:
                    continue

                day_count = 0
                abbrev_count = 0
                for col_idx in range(2, min(len(row), 100)):
                    cell_value = str(row[col_idx]).strip() if col_idx < len(row) else ""
                    day_abbrevs = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"]
                    if cell_value.lower() in day_abbrevs:
                        abbrev_count += 1
                        continue
                    numbers = re.findall(r"\d+", cell_value)
                    if numbers:
                        day = int(numbers[0])
                        if 1 <= day <= 31:
                            day_count += 1

                if day_count >= 5 and abbrev_count < day_count:
                    day_row_idx = row_idx
                    if row_idx > 0:
                        month_row_idx = row_idx - 1
                    break

        if day_row_idx is None:
            logger.warning("Could not find day row")
            return None, {}

        header_row_idx = day_row_idx

        month_row = data[month_row_idx] if month_row_idx is not None else []
        day_row = data[day_row_idx]

        def find_month_for_column(col_idx):
            """Find month for given column"""
            if col_idx < len(month_row):
                month_cell = (
                    str(month_row[col_idx]).strip() if month_row[col_idx] else ""
                )
                if month_cell:
                    month_num = self._parse_month_name(month_cell)
                    if month_num:
                        return month_num

            for prev_col in range(col_idx - 1, max(1, col_idx - 100), -1):
                if prev_col < len(month_row):
                    prev_month_cell = (
                        str(month_row[prev_col]).strip() if month_row[prev_col] else ""
                    )
                    if prev_month_cell:
                        month_num = self._parse_month_name(prev_month_cell)
                        if month_num:
                            return month_num
            return None

        col_idx = 2
        current_month = None
        last_day = None

        while col_idx < len(day_row) and col_idx < 500:
            day_cell = ""
            if col_idx < len(day_row):
                day_cell = str(day_row[col_idx]).strip() if day_row[col_idx] else ""

            if not day_cell:
                col_idx += 1
                continue

            day_abbrevs = [
                "пн",
                "вт",
                "ср",
                "чт",
                "пт",
                "сб",
                "вс",
                "mon",
                "tue",
                "wed",
                "thu",
                "fri",
                "sat",
                "sun",
            ]
            if day_cell.lower() in day_abbrevs:
                col_idx += 1
                continue

            numbers = re.findall(r"\d+", day_cell)
            if numbers:
                try:
                    day = int(numbers[0])
                    if 1 <= day <= 31:
                        month_for_col = find_month_for_column(col_idx)

                        if month_for_col:
                            current_month = month_for_col

                        if day == 1 and last_day is not None and last_day >= 28:
                            month_for_col = find_month_for_column(col_idx)
                            if month_for_col:
                                current_month = month_for_col
                            else:
                                if current_month:
                                    current_month = (current_month % 12) + 1
                                    if current_month == 1:
                                        current_year += 1

                        if current_month is None:
                            current_month = datetime.now().month

                        date_obj = datetime(current_year, current_month, day).date()
                        date_map[date_obj] = col_idx
                        last_day = day
                except ValueError:
                    pass

            col_idx += 1

        if date_map:
            logger.info(f"Successfully parsed {len(date_map)} dates")
            return header_row_idx, date_map

        return None, {}

    def _is_occupied(self, cell_value: str) -> bool:
        """Check if a cell indicates the room is occupied"""
        if not cell_value:
            return False

        if not isinstance(cell_value, str):
            cell_value = str(cell_value)

        cell_value = cell_value.strip()
        return len(cell_value) > 0

    def load_calendar(
        self,
        spreadsheet_id: str,
        sheet_name: Optional[str] = None,
        date_start_cell: Optional[str] = None,
        date_start: Optional[str] = None,
    ) -> bool:
        """
        Load and parse the booking calendar from Google Sheets

        Args:
            spreadsheet_id: Google Spreadsheet ID
            sheet_name: Optional sheet name
            date_start_cell: Optional start cell for dates (e.g., 'C7').
                           If not provided, uses DATE_START_CELL from env or auto-detects
            date_start: Optional start date (e.g., '24.11.2025').
                       If not provided, uses DATE_START from env or reads from cell
        """
        try:
            range_name = f"{sheet_name}!A:ZZ" if sheet_name else "A:ZZ"

            spreadsheet = (
                self.service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
            )

            sheet_id = None
            for sheet in spreadsheet.get("sheets", []):
                if sheet_name is None or sheet["properties"]["title"] == sheet_name:
                    sheet_id = sheet["properties"]["sheetId"]
                    break

            if sheet_id is None:
                logger.error(f"Sheet '{sheet_name}' not found")
                return False

            result_values = (
                self.service.spreadsheets()
                .values()
                .get(spreadsheetId=spreadsheet_id, range=range_name)
                .execute()
            )

            data = result_values.get("values", [])
            if not data:
                logger.error("No data found in sheet")
                return False

            result_grid = (
                self.service.spreadsheets()
                .get(
                    spreadsheetId=spreadsheet_id,
                    fields="sheets(properties(sheetId,title),merges)",
                )
                .execute()
            )

            self.merged_cells_map = {}
            for sheet in result_grid.get("sheets", []):
                if sheet["properties"]["sheetId"] == sheet_id:
                    for merge in sheet.get("merges", []):
                        start_row = merge["startRowIndex"]
                        end_row = merge["endRowIndex"]
                        start_col = merge["startColumnIndex"]
                        end_col = merge["endColumnIndex"]

                        for row in range(start_row, end_row):
                            for col in range(start_col, end_col):
                                self.merged_cells_map[(row, col)] = (
                                    start_row,
                                    start_col,
                                    end_row,
                                    end_col,
                                )
                    break

            # Determine date start cell and date start value
            # Priority: 1) function parameter, 2) env variable, 3) auto-detect
            final_date_start_cell = date_start_cell or os.getenv("DATE_START_CELL")
            final_date_start = date_start or os.getenv("DATE_START")

            if final_date_start_cell:
                # Use new method: parse dates from specified start cell
                logger.info(f"Using date start cell method: {final_date_start_cell}")
                if final_date_start:
                    logger.info(
                        f"Using start date from parameter/env: {final_date_start}"
                    )
                (
                    self.header_row_index,
                    self.date_column_map,
                ) = self._parse_dates_from_start_cell(
                    data, final_date_start_cell, final_date_start
                )
            else:
                # Use old method: auto-detect header row
                logger.info("Using auto-detect method for date headers")
                self.header_row_index, self.date_column_map = self._find_header_row(
                    data
                )

            if self.header_row_index is None:
                logger.error("Could not find or parse date header row")
                return False

            # Data starts after header row (row 8 = index 7, if header is row 7 = index 6)
            self.data_start_row = self.header_row_index + 1
            self.sheet_data = data

            logger.info(
                f"Header row: {self.header_row_index + 1} (index {self.header_row_index}), Data starts at row: {self.data_start_row + 1} (index {self.data_start_row})"
            )

            if self.date_column_map:
                min_date = min(self.date_column_map.keys())
                max_date = max(self.date_column_map.keys())
                logger.info(f"Loaded calendar: {len(self.date_column_map)} dates found")
                logger.info(f"Date range: {min_date} to {max_date}")

            return True

        except HttpError as error:
            logger.error(f"Error loading calendar: {error}")
            return False

    def _find_date_in_calendar(
        self, target_date: datetime.date, silent: bool = False
    ) -> Optional[datetime.date]:
        """Find a date in the calendar with year-agnostic matching"""
        if target_date in self.date_column_map:
            return target_date

        target_month = target_date.month
        target_day = target_date.day

        matches = []
        for calendar_date in self.date_column_map.keys():
            if calendar_date.month == target_month and calendar_date.day == target_day:
                matches.append(calendar_date)

        if matches:
            best_match = matches[0]
            for match in matches:
                if abs(match.year - target_date.year) < abs(
                    best_match.year - target_date.year
                ):
                    best_match = match
            return best_match

        return None

    def get_available_rooms(
        self,
        check_in: datetime,
        check_out: datetime,
        category_filter: Optional[str] = None,
    ) -> List[Dict[str, str]]:
        """Get all available rooms for a date range"""
        if not hasattr(self, "sheet_data") or self.sheet_data is None:
            raise ValueError("Calendar not loaded. Call load_calendar() first.")

        check_in_date = check_in.date() if isinstance(check_in, datetime) else check_in
        check_out_date = (
            check_out.date() if isinstance(check_out, datetime) else check_out
        )

        dates_to_check = []
        current_date = check_in_date
        while current_date <= check_out_date:
            dates_to_check.append(current_date)
            current_date += timedelta(days=1)

        if not dates_to_check:
            return []

        date_columns = {}
        missing_dates = []
        for date in dates_to_check:
            found_date = self._find_date_in_calendar(date)
            if found_date:
                date_columns[date] = self.date_column_map[found_date]
            else:
                missing_dates.append(date)

        if missing_dates:
            logger.warning(
                f"Some dates not found in calendar: {missing_dates[:5]}{'...' if len(missing_dates) > 5 else ''}"
            )

        if not date_columns:
            logger.warning("No dates from requested range found in calendar")
            return []

        available_rooms = []

        # Determine row range: from data_start_row (row 8, index 7) to row 39 (index 38)
        # But also check if we have data beyond that
        end_row = min(
            len(self.sheet_data), 39
        )  # Row 39 is index 38, but we use < 39, so max is 38
        if self.data_start_row >= end_row:
            logger.warning(
                f"data_start_row ({self.data_start_row}) is >= end_row ({end_row}), no rooms to check"
            )
            return []

        logger.info(
            f"Checking rooms from row {self.data_start_row + 1} to row {end_row} (indices {self.data_start_row} to {end_row - 1})"
        )
        logger.info(
            f"Checking {len(dates_to_check)} dates, {len(date_columns)} dates found in calendar"
        )

        for row_idx in range(self.data_start_row, end_row):
            row = self.sheet_data[row_idx]

            if len(row) < 2:
                continue

            category = str(row[0]).strip() if len(row) > 0 and row[0] else ""
            room_number = str(row[1]).strip() if len(row) > 1 and row[1] else ""

            if not category or not room_number:
                continue

            # Skip legend/header rows
            legend_keywords = ["legend", "легенда", "категория", "category"]
            if (
                category.lower() in legend_keywords
                and not room_number
                or room_number.lower() in legend_keywords
            ):
                continue

            if category.lower() in [
                "категория",
                "category",
            ] and room_number.lower() in ["№ комнаты", "room", "room number", "room #"]:
                continue

            # Apply category filter if specified (empty string or "ALL" means no filter)
            # Normalize "ALL" to be treated as no filter
            if category_filter:
                normalized_filter = category_filter.strip().upper()
                # Skip filtering if "ALL" is specified
                if normalized_filter != "ALL" and category.lower() != category_filter.strip().lower():
                    continue

            is_available = True
            occupied_dates = []
            checked_dates_count = 0

            # Check availability for ALL dates in the range
            # Room is available only if it's free on ALL dates
            for date in dates_to_check:
                if date not in date_columns:
                    # Date not in calendar - skip it but log warning
                    logger.debug(f"Date {date} not found in calendar, skipping")
                    continue

                checked_dates_count += 1
                col_idx = date_columns[date]

                # Check if this cell is part of a merged cell
                actual_row = row_idx
                actual_col = col_idx

                # Check if current cell is in merged range
                if (row_idx, col_idx) in self.merged_cells_map:
                    start_row, start_col, end_row, end_col = self.merged_cells_map[
                        (row_idx, col_idx)
                    ]
                    # Use the start cell where the value is stored
                    actual_row = start_row
                    actual_col = start_col
                    logger.debug(
                        f"Cell ({row_idx}, {col_idx}) is merged, using start cell ({actual_row}, {actual_col})"
                    )

                # Get cell value - handle cases where cell might not exist
                cell_value = ""
                if actual_row < len(self.sheet_data):
                    actual_row_data = self.sheet_data[actual_row]
                    if actual_col < len(actual_row_data):
                        raw_value = actual_row_data[actual_col]
                        # Handle None, empty string, or any other falsy value
                        if raw_value is not None:
                            cell_value = str(raw_value).strip()
                        # If raw_value is None or empty, cell_value stays as ""

                # Check if occupied - if ANY date is occupied, room is not available
                if self._is_occupied(cell_value):
                    is_available = False
                    occupied_dates.append(date)
                    # Break early if we found an occupied date
                    logger.debug(
                        f"Room {room_number} ({category}) occupied on {date} (col {col_idx}, row {row_idx}, cell value: '{cell_value[:50]}')"
                    )
                    break  # No need to check remaining dates if one is occupied
            
            # Only add room if it's available on ALL checked dates
            # If we didn't check any dates (all were missing from calendar), skip this room
            if is_available and checked_dates_count > 0:
                available_rooms.append({"category": category, "room": room_number})
            elif not is_available:
                logger.debug(
                    f"Room {room_number} ({category}) not available - occupied on: {occupied_dates[:3]}{'...' if len(occupied_dates) > 3 else ''}"
                )
            elif checked_dates_count == 0:
                logger.debug(
                    f"Room {room_number} ({category}) skipped - no dates from requested range found in calendar"
                )

        logger.info(
            f"Found {len(available_rooms)} available rooms out of {end_row - self.data_start_row} checked"
        )
        return available_rooms

    def check_room_availability(self, room_number: str, date: datetime) -> bool:
        """Check if a specific room is available on a specific date"""
        if not hasattr(self, "sheet_data") or self.sheet_data is None:
            raise ValueError("Calendar not loaded. Call load_calendar() first.")

        check_date = date.date() if isinstance(date, datetime) else date

        found_date = self._find_date_in_calendar(check_date, silent=True)
        if not found_date:
            return False

        col_idx = self.date_column_map[found_date]

        for row_idx in range(self.data_start_row, len(self.sheet_data)):
            row = self.sheet_data[row_idx]

            if len(row) < 2:
                continue

            room = str(row[1]).strip() if len(row) > 1 and row[1] else ""

            if room.lower() == room_number.lower():
                actual_row = row_idx
                actual_col = col_idx

                if (row_idx, col_idx) in self.merged_cells_map:
                    start_row, start_col, end_row, end_col = self.merged_cells_map[
                        (row_idx, col_idx)
                    ]
                    actual_row = start_row
                    actual_col = start_col

                cell_value = ""
                if actual_row < len(self.sheet_data):
                    actual_row_data = self.sheet_data[actual_row]
                    if actual_col < len(actual_row_data):
                        cell_value = (
                            str(actual_row_data[actual_col]).strip()
                            if actual_row_data[actual_col]
                            else ""
                        )

                return not self._is_occupied(cell_value)

        return False

    def get_available_categories(
        self, check_in: datetime, check_out: datetime
    ) -> List[str]:
        """Get list of categories that have at least one available room"""
        available_rooms = self.get_available_rooms(check_in, check_out)
        categories = set(room["category"] for room in available_rooms)
        return sorted(list(categories))

    def get_calendar_info(self) -> Dict:
        """Get information about loaded calendar"""
        if not hasattr(self, "date_column_map") or not self.date_column_map:
            return {}

        dates = sorted(self.date_column_map.keys())
        return {
            "total_dates": len(dates),
            "date_range": {"min_date": str(dates[0]), "max_date": str(dates[-1])},
            "years": sorted(set(d.year for d in dates)),
            "header_row": self.header_row_index + 1
            if self.header_row_index is not None
            else None,
            "data_start_row": self.data_start_row + 1
            if self.data_start_row is not None
            else None,
            "sample_dates": [str(d) for d in dates[:10]]
            if len(dates) > 10
            else [str(d) for d in dates],
        }
