import logging
import os
import re
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

from dotenv import load_dotenv
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

load_dotenv()

logger = logging.getLogger(__name__)

MONTHS = {
    "январь": 1,
    "февраль": 2,
    "март": 3,
    "апрель": 4,
    "май": 5,
    "июнь": 6,
    "июль": 7,
    "август": 8,
    "сентябрь": 9,
    "октябрь": 10,
    "ноябрь": 11,
    "декабрь": 12,
}

DAYS = {
    "пн",
    "вт",
    "ср",
    "чт",
    "пт",
    "сб",
    "вс",
}


class Parser:
    def __init__(self):
        self.service = self._authenticate()
        self.date_column_map: Dict[datetime.date, int] = {}
        self.header_row_index: Optional[int] = None
        self.data_start_row: Optional[int] = None
        self.merged_cells_map: Dict[Tuple[int, int], Tuple[int, int]] = {}
        self.sheet_data: Optional[List[List]] = None

    def _authenticate(self):
        credentials_path = os.getenv("GOOGLE_CREDENTIALS_PATH")
        if not credentials_path or not os.path.exists(credentials_path):
            raise ValueError("GOOGLE_CREDENTIALS_PATH is required")

        credentials = service_account.Credentials.from_service_account_file(
            credentials_path,
            scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"],
        )
        return build("sheets", "v4", credentials=credentials)

    def _parse_date(
        self,
        date_str: Optional[str],
        default_month: Optional[int] = None,
        default_year: Optional[int] = None,
    ) -> Optional[datetime]:
        if not date_str:
            return None

        default_year = default_year or datetime.now().year
        formats = ("%d.%m.%Y", "%d/%m/%Y", "%Y-%m-%d", "%d.%m", "%d/%m")

        for fmt in formats:
            try:
                parsed = datetime.strptime(date_str, fmt)
                if parsed.year == 1900:
                    parsed = parsed.replace(year=default_year)
                return parsed
            except ValueError:
                continue

        text_month_match = re.search(r"([A-Za-zА-Яа-яЁё]+)", date_str)
        day_match = re.search(r"\d{1,2}", date_str)
        if text_month_match and day_match:
            month = MONTHS.get(text_month_match.group(1).lower())
            if month:
                year_match = re.search(r"\d{4}", date_str)
                year = int(year_match.group()) if year_match else default_year
                return datetime(year, month, int(day_match.group()))

        numbers = re.findall(r"\d+", date_str)
        if numbers:
            day = int(numbers[0])
            if 1 <= day <= 31:
                month = default_month or datetime.now().month
                return datetime(default_year, month, day)
        return None

    def _cell_to_indices(self, cell_ref: str) -> Tuple[int, int]:
        match = re.match(r"^([A-Z]+)(\d+)$", cell_ref.upper())
        if not match:
            raise ValueError(f"Invalid cell reference: {cell_ref}")

        col_letters, row_number = match.group(1), int(match.group(2))
        col_idx = 0
        for char in col_letters:
            col_idx = col_idx * 26 + (ord(char) - ord("A") + 1)
        return row_number - 1, col_idx - 1

    def _parse_dates_from_start_cell(
        self, data: List[List], start_cell: str, start_date_str: Optional[str]
    ) -> Tuple[int, Dict[datetime.date, int]]:
        start_row_idx, start_col_idx = self._cell_to_indices(start_cell)
        if start_row_idx >= len(data):
            raise ValueError("DATE_START_CELL points outside the sheet data")

        start_date = self._parse_date(start_date_str)
        if not start_date:
            cell_value = (
                data[start_row_idx][start_col_idx]
                if start_col_idx < len(data[start_row_idx])
                else ""
            )
            start_date = self._parse_date(str(cell_value)) if cell_value else None

        if not start_date:
            raise ValueError("DATE_START could not be parsed")

        date_map: Dict[datetime.date, int] = {}
        current_date = start_date.date()
        row = data[start_row_idx]

        for col_idx in range(start_col_idx, len(row)):
            raw_value = row[col_idx] if col_idx < len(row) else ""
            cell_value = str(raw_value).strip() if raw_value is not None else ""
            if not cell_value:
                break
            if cell_value.lower() in DAYS:
                continue
            date_map[current_date] = col_idx
            current_date += timedelta(days=1)

        if not date_map:
            raise ValueError("No dates parsed from DATE_START_CELL row")

        return start_row_idx, date_map

    def _find_date_in_calendar(self, target_date: datetime.date) -> Optional[datetime]:
        if target_date in self.date_column_map:
            return target_date

        candidates = [
            calendar_date
            for calendar_date in self.date_column_map
            if calendar_date.month == target_date.month
            and calendar_date.day == target_date.day
        ]
        if not candidates:
            return None

        return min(candidates, key=lambda d: abs(d.year - target_date.year))

    def _get_cell_value(self, row_idx: int, col_idx: int) -> str:
        actual_row, actual_col = self.merged_cells_map.get(
            (row_idx, col_idx), (row_idx, col_idx)
        )
        if actual_row < len(self.sheet_data or []) and actual_col < len(
            self.sheet_data[actual_row]
        ):
            raw = self.sheet_data[actual_row][actual_col]
            return str(raw).strip() if raw is not None else ""
        return ""

    def load_calendar(
        self,
        spreadsheet_id: str,
        sheet_name: Optional[str] = None,
        date_start_cell: Optional[str] = None,
        date_start: Optional[str] = None,
    ) -> bool:
        start_cell = date_start_cell or os.getenv("DATE_START_CELL")
        if not start_cell:
            raise ValueError("DATE_START_CELL is required")

        start_date_value = date_start or os.getenv("DATE_START")
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
            raise ValueError(f"Sheet '{sheet_name}' not found")

        values_response = (
            self.service.spreadsheets()
            .values()
            .get(spreadsheetId=spreadsheet_id, range=range_name)
            .execute()
        )
        self.sheet_data = values_response.get("values", [])
        if not self.sheet_data:
            raise ValueError("Sheet is empty")

        grid_response = (
            self.service.spreadsheets()
            .get(
                spreadsheetId=spreadsheet_id,
                fields="sheets(properties(sheetId,title),merges)",
            )
            .execute()
        )

        self.merged_cells_map = {}
        for sheet in grid_response.get("sheets", []):
            if sheet["properties"]["sheetId"] == sheet_id:
                for merge in sheet.get("merges", []):
                    start_row = merge["startRowIndex"]
                    end_row = merge["endRowIndex"]
                    start_col = merge["startColumnIndex"]
                    end_col = merge["endColumnIndex"]
                    for row in range(start_row, end_row):
                        for col in range(start_col, end_col):
                            self.merged_cells_map[(row, col)] = (start_row, start_col)
                break

        self.header_row_index, self.date_column_map = self._parse_dates_from_start_cell(
            self.sheet_data, start_cell, start_date_value
        )
        self.data_start_row = self.header_row_index + 1

        logger.info(
            "Calendar loaded: %s dates, header row %s, data starts at row %s",
            len(self.date_column_map),
            self.header_row_index + 1,
            self.data_start_row + 1,
        )
        return True

    def check_connection(self, spreadsheet_id: Optional[str] = None) -> Dict:
        if not self.service:
            raise ValueError("Service not initialized")

        result = {
            "connected": True,
            "authenticated": True,
            "message": "Authenticated with Google Sheets API",
            "spreadsheet_accessible": None,
            "spreadsheet_title": None,
            "error": None,
        }

        if not spreadsheet_id:
            return result

        try:
            spreadsheet = (
                self.service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
            )
            result["spreadsheet_accessible"] = True
            result["spreadsheet_title"] = spreadsheet.get("properties", {}).get("title")
            result["message"] = "Spreadsheet access confirmed"
        except HttpError as e:
            result["spreadsheet_accessible"] = False
            result["error"] = f"HTTP {e.resp.status}: {e}"
            result["message"] = "Authenticated, but spreadsheet access failed"
        except Exception as e:
            result["spreadsheet_accessible"] = False
            result["error"] = str(e)
            result["message"] = "Authenticated, but spreadsheet access failed"

        return result

    def get_available_rooms(
        self,
        check_in: datetime,
        check_out: datetime,
        category_filter: Optional[str] = None,
    ) -> List[Dict[str, str]]:
        if not self.sheet_data:
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

        date_columns: Dict[datetime.date, int] = {}
        for date in dates_to_check:
            found_date = self._find_date_in_calendar(date)
            if found_date:
                date_columns[date] = self.date_column_map[found_date]

        if not date_columns:
            return []

        available_rooms: List[Dict[str, str]] = []
        category_filter_norm = category_filter.casefold() if category_filter else None
        for row_idx in range(self.data_start_row, len(self.sheet_data or [])):
            row = self.sheet_data[row_idx]
            if len(row) < 2:
                continue

            category = str(row[0]).strip()
            room_number = str(row[1]).strip()
            if not category or not room_number:
                continue

            if (
                category_filter_norm
                and category.casefold() != category_filter_norm
                and category_filter_norm != "all"
            ):
                continue

            is_available = True
            for date in dates_to_check:
                col_idx = date_columns.get(date)
                if col_idx is None:
                    continue

                cell_value = self._get_cell_value(row_idx, col_idx)
                if cell_value:
                    is_available = False
                    break

            if is_available:
                available_rooms.append({"category": category, "room": room_number})

        return available_rooms

    def get_calendar_info(self) -> Dict:
        if not self.date_column_map:
            return {}

        dates = sorted(self.date_column_map.keys())
        return {
            "total_dates": len(dates),
            "date_range": {"min_date": str(dates[0]), "max_date": str(dates[-1])},
            "years": sorted({d.year for d in dates}),
            "header_row": self.header_row_index + 1
            if self.header_row_index is not None
            else None,
            "data_start_row": self.data_start_row + 1
            if self.data_start_row is not None
            else None,
        }
