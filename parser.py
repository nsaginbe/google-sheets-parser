import os
from datetime import datetime, timedelta
from dotenv import load_dotenv
from google.oauth2.credentials import Credentials
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from typing import List, Dict, Optional, Tuple
import re

# Load environment variables from .env file
load_dotenv()

class HotelBookingParser:
    def __init__(self):
        """Initialize Google Sheets API client"""
        self.service = None
        self._authenticate()
        self.date_column_map = {}  # Maps date -> column index (0-based)
        self.header_row_index = None
        self.data_start_row = None
        self.merged_cells_map = {}  # Maps (row, col) -> (start_row, start_col, end_row, end_col) for merged cells
        self.sheet_data = None
    
    def _authenticate(self):
        """Authenticate with Google Sheets API"""
        try:
            # Option 1: Service Account (recommended for server-side)
            credentials_path = os.getenv('GOOGLE_CREDENTIALS_PATH')
            if credentials_path and os.path.exists(credentials_path):
                credentials = service_account.Credentials.from_service_account_file(
                    credentials_path,
                    scopes=['https://www.googleapis.com/auth/spreadsheets.readonly']
                )
                self.service = build('sheets', 'v4', credentials=credentials)
                print("Authenticated using service account")
                return
            
            # Option 2: OAuth2 Credentials (for user-based access)
            creds_json = os.getenv('GOOGLE_CREDENTIALS_JSON')
            if creds_json:
                import json
                creds_dict = json.loads(creds_json)
                credentials = Credentials.from_authorized_user_info(
                    creds_dict,
                    scopes=['https://www.googleapis.com/auth/spreadsheets.readonly']
                )
                self.service = build('sheets', 'v4', credentials=credentials)
                print("Authenticated using OAuth2 credentials")
                return
            
            raise ValueError("No valid credentials found. Set GOOGLE_CREDENTIALS_PATH or GOOGLE_CREDENTIALS_JSON in .env")
        
        except Exception as e:
            print(f"Authentication error: {e}")
            raise
    
    def _parse_month_name(self, text: str) -> Optional[int]:
        """Parse month name to month number (1-12)"""
        if not text or not isinstance(text, str):
            return None
        
        text = text.strip().lower()
        
        # Russian month names
        months_ru = {
            'январь': 1, 'янв': 1,
            'февраль': 2, 'фев': 2,
            'март': 3, 'мар': 3,
            'апрель': 4, 'апр': 4,
            'май': 5,
            'июнь': 6, 'июн': 6,
            'июль': 7, 'июл': 7,
            'август': 8, 'авг': 8,
            'сентябрь': 9, 'сен': 9,
            'октябрь': 10, 'окт': 10,
            'ноябрь': 11, 'ноя': 11,
            'декабрь': 12, 'дек': 12,
        }
        
        # English month names
        months_en = {
            'january': 1, 'jan': 1,
            'february': 2, 'feb': 2,
            'march': 3, 'mar': 3,
            'april': 4, 'apr': 4,
            'may': 5,
            'june': 6, 'jun': 6,
            'july': 7, 'jul': 7,
            'august': 8, 'aug': 8,
            'september': 9, 'sep': 9,
            'october': 10, 'oct': 10,
            'november': 11, 'nov': 11,
            'december': 12, 'dec': 12,
        }
        
        if text in months_ru:
            return months_ru[text]
        if text in months_en:
            return months_en[text]
        
        return None
    
    def _parse_date(self, date_str: str, default_month: Optional[int] = None, default_year: Optional[int] = None) -> Optional[datetime]:
        """Parse date from various formats (e.g., '21', '1', '21.07', '2024-07-21')"""
        if not date_str or not isinstance(date_str, str):
            return None
        
        # Remove whitespace
        date_str = date_str.strip()
        
        # Use current year if not provided
        if default_year is None:
            default_year = datetime.now().year
        
        # Try different date formats
        formats = [
            '%d.%m.%Y',     # Day.Month.Year
            '%d/%m/%Y',     # Day/Month/Year
            '%Y-%m-%d',     # ISO format
            '%d.%m',        # Day.Month (use default year)
            '%d/%m',        # Day/Month (use default year)
        ]
        
        for fmt in formats:
            try:
                parsed = datetime.strptime(date_str, fmt)
                if default_year and parsed.year == 1900:  # strptime default year
                    parsed = parsed.replace(year=default_year)
                return parsed
            except ValueError:
                continue
        
        # Try to extract just numbers (day of month)
        numbers = re.findall(r'\d+', date_str)
        if numbers:
            try:
                day = int(numbers[0])
                if 1 <= day <= 31:
                    month = default_month if default_month else datetime.now().month
                    return datetime(default_year, month, day)
            except ValueError:
                pass
        
        return None
    
    def _find_header_row(self, data: List[List]) -> Tuple[int, Dict[datetime.date, int]]:
        """
        Find date headers and map dates to column indices.
        Начиная с колонки C (индекс 2) идет вправо, каждой колонке присваивается дата.
        Строка 9 содержит месяцы, строка 10 содержит дни.
        Returns: (header_row_index, date_column_map)
        """
        date_map = {}
        header_row_idx = None
        current_year = datetime.now().year
        
        # Отладка: показываем первые строки
        print(f"\n🔍 Debug: Checking first {min(15, len(data))} rows for date headers...")
        
        month_row_idx = None
        day_row_idx = None
        
        # Ищем строку с месяцами (строка 9, индекс 8)
        for row_idx in range(min(15, len(data))):
            row = data[row_idx]
            if len(row) < 3:
                continue
            
            # Проверяем есть ли месяцы в колонках начиная с C
            month_count = 0
            found_months = []
            for col_idx in range(2, min(len(row), 100)):
                cell_value = str(row[col_idx]).strip() if col_idx < len(row) else ""
                month_num = self._parse_month_name(cell_value)
                if month_num:
                    month_count += 1
                    found_months.append((col_idx, cell_value, month_num))
            
            if month_count > 0:
                month_row_idx = row_idx
                print(f"✅ Found month row at index {row_idx} (1-based: {row_idx + 1}): {found_months[:3]}")
                # Строка с днями может быть через одну строку (строка 6 - сокращения, строка 7 - числа)
                # Проверяем строку +2 (строка 7)
                if row_idx + 2 < len(data):
                    # Проверяем есть ли числа в строке +2
                    check_row = data[row_idx + 2]
                    day_numbers = 0
                    for check_col in range(2, min(len(check_row), 50)):
                        check_cell = str(check_row[check_col]).strip() if check_col < len(check_row) else ""
                        numbers = re.findall(r'\d+', check_cell)
                        if numbers:
                            day = int(numbers[0])
                            if 1 <= day <= 31:
                                day_numbers += 1
                    
                    if day_numbers >= 5:
                        day_row_idx = row_idx + 2
                        print(f"✅ Found day row at index {day_row_idx} (1-based: {day_row_idx + 1}) - numbers found")
                    elif row_idx + 1 < len(data):
                        day_row_idx = row_idx + 1
                        print(f"✅ Using next row as day row: index {day_row_idx} (1-based: {day_row_idx + 1})")
                elif row_idx + 1 < len(data):
                    day_row_idx = row_idx + 1
                    print(f"✅ Using next row as day row: index {day_row_idx} (1-based: {day_row_idx + 1})")
                break
        
        # Если не нашли по месяцам, ищем строку с днями напрямую
        if day_row_idx is None:
            print("⚠️  Month row not found, searching for day row directly...")
            for row_idx in range(min(20, len(data))):
                row = data[row_idx]
                if len(row) < 3:
                    continue
                
                # Ищем строку с числами (дни месяца), пропускаем строки только с сокращениями
                day_count = 0
                abbrev_count = 0
                found_days = []
                for col_idx in range(2, min(len(row), 100)):
                    cell_value = str(row[col_idx]).strip() if col_idx < len(row) else ""
                    # Пропускаем сокращения дней недели
                    day_abbrevs = ['пн', 'вт', 'ср', 'чт', 'пт', 'сб', 'вс']
                    if cell_value.lower() in day_abbrevs:
                        abbrev_count += 1
                        continue
                    # Пробуем распарсить как число (день)
                    numbers = re.findall(r'\d+', cell_value)
                    if numbers:
                        day = int(numbers[0])
                        if 1 <= day <= 31:
                            day_count += 1
                            if len(found_days) < 5:
                                found_days.append((col_idx, cell_value, day))
                
                # Если нашли достаточно чисел И не только сокращения
                if day_count >= 5 and abbrev_count < day_count:
                    day_row_idx = row_idx
                    print(f"✅ Found day row at index {row_idx} (1-based: {row_idx + 1}): {found_days}")
                    # Строка выше должна быть с месяцами
                    if row_idx > 0:
                        month_row_idx = row_idx - 1
                    break
        
        if day_row_idx is None:
            print("❌ Could not find day row. Showing sample of first rows:")
            for i in range(min(12, len(data))):
                row = data[i]
                sample = [str(cell)[:20] if cell else "" for cell in row[:10]]
                print(f"  Row {i+1}: {sample}")
            return None, {}
        
        header_row_idx = day_row_idx
        
        # Теперь парсим: начиная с колонки C (индекс 2) идем вправо
        # Для каждой колонки создаем полную дату: год + месяц + день
        current_year = datetime.now().year
        
        month_row = data[month_row_idx] if month_row_idx is not None else []
        day_row = data[day_row_idx]
        
        print(f"📅 Parsing dates starting from column C (index 2)...")
        print(f"   Month row: {month_row_idx + 1 if month_row_idx is not None else 'None'}")
        print(f"   Day row: {day_row_idx + 1}")
        print(f"   Day row length: {len(day_row)}")
        
        # Показываем первые 30 ячеек строки с днями для отладки
        print(f"\n🔍 Debug: First 30 cells of day row (starting from column C):")
        for i in range(2, min(32, len(day_row))):
            cell_val = day_row[i] if i < len(day_row) else ""
            cell_str = str(cell_val).strip() if cell_val else ""
            col_letter = self._col_index_to_letter(i)
            print(f"   {col_letter}{day_row_idx + 1} (idx {i}): '{cell_str}' (type: {type(cell_val).__name__})")
        
        # Показываем первые 30 ячеек строки с месяцами
        if month_row_idx is not None:
            print(f"\n🔍 Debug: First 30 cells of month row:")
            for i in range(2, min(32, len(month_row))):
                cell_val = month_row[i] if i < len(month_row) else ""
                cell_str = str(cell_val).strip() if cell_val else ""
                col_letter = self._col_index_to_letter(i)
                print(f"   {col_letter}{month_row_idx + 1} (idx {i}): '{cell_str}'")
        
        # Вспомогательная функция для поиска месяца для колонки
        def find_month_for_column(col_idx):
            """Найти месяц для данной колонки (ищет в обратном направлении из-за объединенных ячеек)"""
            # Сначала проверяем текущую колонку
            if col_idx < len(month_row):
                month_cell = str(month_row[col_idx]).strip() if month_row[col_idx] else ""
                if month_cell:
                    month_num = self._parse_month_name(month_cell)
                    if month_num:
                        return month_num
            
            # Если не нашли, ищем в обратном направлении (объединенные ячейки)
            for prev_col in range(col_idx - 1, max(1, col_idx - 100), -1):
                if prev_col < len(month_row):
                    prev_month_cell = str(month_row[prev_col]).strip() if month_row[prev_col] else ""
                    if prev_month_cell:
                        month_num = self._parse_month_name(prev_month_cell)
                        if month_num:
                            return month_num
            return None
        
        # Идем вправо начиная с колонки C (индекс 2)
        col_idx = 2  # Колонка C
        dates_found = 0
        current_month = None
        last_day = None
        skipped_count = 0
        empty_count = 0
        
        print(f"\n🔍 Debug: Processing columns starting from C (index 2)...")
        
        while col_idx < len(day_row) and col_idx < 500:
            # Берем день из строки 10
            day_cell = ""
            if col_idx < len(day_row):
                day_cell = str(day_row[col_idx]).strip() if day_row[col_idx] else ""
            
            # Логируем первые 20 колонок для отладки
            if col_idx < 22:
                col_letter = self._col_index_to_letter(col_idx)
                print(f"   Column {col_letter} (idx {col_idx}): cell='{day_cell}'")
            
            # Если ячейка пустая
            if not day_cell:
                empty_count += 1
                col_idx += 1
                continue
            
            # Пропускаем сокращения дней недели
            day_abbrevs = ['пн', 'вт', 'ср', 'чт', 'пт', 'сб', 'вс', 
                          'mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun']
            if day_cell.lower() in day_abbrevs:
                skipped_count += 1
                if col_idx < 22:
                    print(f"      -> Skipped (day abbreviation)")
                col_idx += 1
                continue
            
            # Пробуем извлечь число (день месяца)
            numbers = re.findall(r'\d+', day_cell)
            if numbers:
                try:
                    day = int(numbers[0])
                    if 1 <= day <= 31:
                        if col_idx < 22:
                            print(f"      -> Found day number: {day}")
                        # Ищем месяц для этой колонки
                        month_for_col = find_month_for_column(col_idx)
                        
                        if col_idx < 22:
                            print(f"      -> Month for column: {month_for_col}")
                        
                        # Если нашли месяц, обновляем current_month
                        if month_for_col:
                            current_month = month_for_col
                        
                        # Если видим день 1 после дней 28-31, это новый месяц
                        if day == 1 and last_day is not None and last_day >= 28:
                            # Новый месяц начался
                            month_for_col = find_month_for_column(col_idx)
                            if month_for_col:
                                current_month = month_for_col
                            else:
                                # Увеличиваем месяц на 1
                                if current_month:
                                    current_month = (current_month % 12) + 1
                                    if current_month == 1:
                                        current_year += 1
                        
                        # Если все еще нет месяца, используем текущий
                        if current_month is None:
                            current_month = datetime.now().month
                            print(f"⚠️  No month found for column {col_idx}, using current month: {current_month}")
                        
                        # Создаем полную дату: год + месяц + день
                        date_obj = datetime(current_year, current_month, day).date()
                        date_map[date_obj] = col_idx
                        dates_found += 1
                        last_day = day
                        
                        if dates_found <= 10:
                            col_letter = self._col_index_to_letter(col_idx)
                            print(f"      -> ✅ Created date: {date_obj} -> column {col_letter}")
                    else:
                        if col_idx < 22:
                            print(f"      -> ❌ Day number {day} out of range (1-31)")
                except ValueError as e:
                    if col_idx < 22:
                        print(f"      -> ❌ ValueError: {e}")
            else:
                if col_idx < 22:
                    print(f"      -> ❌ No numbers found in '{day_cell}'")
            
            col_idx += 1
        
        print(f"\n📊 Summary:")
        print(f"   Total columns checked: {col_idx - 2}")
        print(f"   Empty cells: {empty_count}")
        print(f"   Skipped (day abbrevs): {skipped_count}")
        print(f"   Dates found: {dates_found}")
        
        if date_map:
            print(f"✅ Successfully parsed {len(date_map)} dates")
            return header_row_idx, date_map
        
        print(f"❌ No dates found. Checked up to column {col_idx}")
        return None, {}
    
    def _col_index_to_letter(self, col_idx: int) -> str:
        """Convert 0-based column index to Excel column letter (A, B, C, ..., Z, AA, AB, ...)"""
        result = ""
        col_idx += 1  # Convert to 1-based
        while col_idx > 0:
            col_idx -= 1
            result = chr(65 + (col_idx % 26)) + result
            col_idx //= 26
        return result
    
    def _is_occupied(self, cell_value: str) -> bool:
        """
        Check if a cell indicates the room is occupied.
        Правило: если в ячейке хоть что-то написано - она занята.
        Объединенные ячейки тоже считаются занятыми (в них есть текст в первой ячейке).
        """
        if not cell_value:
            return False
        
        # Преобразуем в строку если это не строка
        if not isinstance(cell_value, str):
            cell_value = str(cell_value)
        
        cell_value = cell_value.strip()
        
        # Пустая ячейка = свободна
        if not cell_value:
            return False
        
        # Если в ячейке есть хоть какой-то текст - она занята
        # Это включает:
        # - Имена гостей
        # - Специальные метки (ремонт, бронь, и т.д.)
        # - Любой другой текст
        return len(cell_value) > 0
    
    def load_calendar(self, spreadsheet_id: str, sheet_name: str = None) -> bool:
        """
        Load and parse the booking calendar from Google Sheets.
        Uses includeGridData=True to get merged cells information.
        Returns True if successful, False otherwise.
        """
        try:
            # Read the entire sheet with grid data to get merged cells info
            if sheet_name:
                range_name = f"{sheet_name}!A:ZZ"
            else:
                range_name = "A:ZZ"
            
            # Get sheet ID first
            spreadsheet = self.service.spreadsheets().get(
                spreadsheetId=spreadsheet_id
            ).execute()
            
            # Find the sheet by name or use first sheet
            sheet_id = None
            for sheet in spreadsheet.get('sheets', []):
                if sheet_name is None or sheet['properties']['title'] == sheet_name:
                    sheet_id = sheet['properties']['sheetId']
                    break
            
            if sheet_id is None:
                print(f"Sheet '{sheet_name}' not found")
                return False
            
            # Get values (for data)
            result_values = self.service.spreadsheets().values().get(
                spreadsheetId=spreadsheet_id,
                range=range_name
            ).execute()
            
            data = result_values.get('values', [])
            if not data:
                print("No data found in sheet")
                return False
            
            # Get merged cells information
            # We use get() to get sheet structure including merges
            result_grid = self.service.spreadsheets().get(
                spreadsheetId=spreadsheet_id,
                fields='sheets(properties(sheetId,title),merges)'
            ).execute()
            
            # Extract merged cells
            self.merged_cells_map = {}
            merged_ranges_count = 0
            for sheet in result_grid.get('sheets', []):
                if sheet['properties']['sheetId'] == sheet_id:
                    for merge in sheet.get('merges', []):
                        start_row = merge['startRowIndex']
                        end_row = merge['endRowIndex']
                        start_col = merge['startColumnIndex']
                        end_col = merge['endColumnIndex']
                        
                        merged_ranges_count += 1
                        # Map all cells in merged range to the start cell coordinates
                        for row in range(start_row, end_row):
                            for col in range(start_col, end_col):
                                self.merged_cells_map[(row, col)] = (start_row, start_col, end_row, end_col)
                    
                    break
            
            print(f"📋 Loaded {merged_ranges_count} merged cell ranges ({len(self.merged_cells_map)} cells mapped)")
            
            # Find the header row with dates
            self.header_row_index, self.date_column_map = self._find_header_row(data)
            
            if self.header_row_index is None:
                print("Could not find date header row")
                return False
            
            # Data starts after the header row
            self.data_start_row = self.header_row_index + 1
            self.sheet_data = data
            
            # Show date range found
            if self.date_column_map:
                min_date = min(self.date_column_map.keys())
                max_date = max(self.date_column_map.keys())
                print(f"Loaded calendar: {len(self.date_column_map)} dates found")
                print(f"Date range: {min_date} to {max_date}")
                print(f"Header row: {self.header_row_index + 1}, Data starts at row: {self.data_start_row + 1}")
                
                # Debug: Show sample of parsed dates
                sample_dates = sorted(self.date_column_map.keys())[:10]
                if len(self.date_column_map) > 10:
                    print(f"Sample dates: {[str(d) for d in sample_dates]} ... (and {len(self.date_column_map) - 10} more)")
                else:
                    print(f"All dates: {[str(d) for d in sorted(self.date_column_map.keys())]}")
            else:
                print(f"Loaded calendar: {len(self.date_column_map)} dates found")
                print(f"Header row: {self.header_row_index + 1}, Data starts at row: {self.data_start_row + 1}")
            
            return True
            
        except HttpError as error:
            print(f"Error loading calendar: {error}")
            return False
    
    def _find_date_in_calendar(self, target_date: datetime.date, silent: bool = False) -> Optional[datetime.date]:
        """
        Find a date in the calendar, trying year-agnostic matching if exact match fails.
        Returns the actual date from calendar if found, None otherwise.
        
        Args:
            target_date: The date to find
            silent: If True, don't print warnings
        """
        # Try exact match first
        if target_date in self.date_column_map:
            return target_date
        
        # Try year-agnostic matching (match by month and day)
        target_month = target_date.month
        target_day = target_date.day
        
        matches = []
        for calendar_date in self.date_column_map.keys():
            if calendar_date.month == target_month and calendar_date.day == target_day:
                matches.append(calendar_date)
        
        if matches:
            # Use the closest year match (prefer same year if multiple years exist)
            best_match = matches[0]
            for match in matches:
                if abs(match.year - target_date.year) < abs(best_match.year - target_date.year):
                    best_match = match
            
            if not silent:
                if len(matches) > 1:
                    print(f"⚠️  Date {target_date} not found, but found {best_match} (same month/day)")
                else:
                    print(f"⚠️  Date {target_date} not found, but found {best_match} (same month/day, different year)")
                print(f"   Using {best_match} from calendar")
            return best_match
        
        return None
    
    def get_available_rooms(
        self, 
        check_in: datetime, 
        check_out: datetime,
        category_filter: Optional[str] = None
    ) -> List[Dict[str, str]]:
        """
        Get all available rooms for a date range.
        
        Args:
            check_in: Check-in date (inclusive)
            check_out: Check-out date (inclusive, room must be free on this date too)
            category_filter: Optional category to filter by (e.g., "Deluxe")
        
        Returns:
            List of available rooms: [{"category": "Deluxe", "room": "A-103"}, ...]
        """
        if not hasattr(self, 'sheet_data') or self.sheet_data is None:
            raise ValueError("Calendar not loaded. Call load_calendar() first.")
        
        check_in_date = check_in.date() if isinstance(check_in, datetime) else check_in
        check_out_date = check_out.date() if isinstance(check_out, datetime) else check_out
        
        # Generate list of dates to check (check-in to check-out, inclusive)
        dates_to_check = []
        current_date = check_in_date
        while current_date <= check_out_date:
            dates_to_check.append(current_date)
            current_date += timedelta(days=1)
        
        if not dates_to_check:
            return []
        
        # Find column indices for all dates (with year-agnostic matching)
        date_columns = {}
        missing_dates = []
        for date in dates_to_check:
            found_date = self._find_date_in_calendar(date)
            if found_date:
                date_columns[date] = self.date_column_map[found_date]
            else:
                missing_dates.append(date)
        
        if missing_dates:
            print(f"❌ Warning: Some dates not found in calendar: {missing_dates}")
            if not date_columns:
                print(f"💡 Tip: Calendar contains dates from {min(self.date_column_map.keys())} to {max(self.date_column_map.keys())}")
                return []
        
        available_rooms = []
        
        # Iterate through data rows (skip header rows)
        for row_idx in range(self.data_start_row, len(self.sheet_data)):
            row = self.sheet_data[row_idx]
            
            # Need at least columns A and B
            if len(row) < 2:
                continue
            
            # Get category (Column A, index 0)
            category = str(row[0]).strip() if len(row) > 0 and row[0] else ""
            
            # Get room number (Column B, index 1)
            room_number = str(row[1]).strip() if len(row) > 1 and row[1] else ""
            
            # Skip rows without category or room number
            if not category or not room_number:
                continue
            
            # Skip legend rows (usually at the top)
            legend_keywords = ['legend', 'легенда', 'категория', 'category']
            if category.lower() in legend_keywords and not room_number or room_number.lower() in legend_keywords:
                continue
            
            # Skip header-like rows
            if category.lower() in ['категория', 'category'] and room_number.lower() in ['№ комнаты', 'room', 'room number', 'room #']:
                continue
            
            # Apply category filter if specified
            if category_filter and category.lower() != category_filter.lower():
                continue
            
            # Check if room is available for all dates in range
            is_available = True
            for date in dates_to_check:
                if date not in date_columns:
                    # Date not in calendar, skip this date
                    continue
                
                col_idx = date_columns[date]
                
                # Check if this cell is part of a merged cell
                # If merged, get value from the start cell of the merge
                actual_row = row_idx
                actual_col = col_idx
                
                if (row_idx, col_idx) in self.merged_cells_map:
                    # This cell is part of a merged range
                    start_row, start_col, end_row, end_col = self.merged_cells_map[(row_idx, col_idx)]
                    # Use the start cell (where the value is)
                    actual_row = start_row
                    actual_col = start_col
                
                # Get cell value from the actual cell (start cell if merged)
                cell_value = ""
                if actual_row < len(self.sheet_data):
                    actual_row_data = self.sheet_data[actual_row]
                    if actual_col < len(actual_row_data):
                        cell_value = str(actual_row_data[actual_col]).strip() if actual_row_data[actual_col] else ""
                
                # Check if occupied
                if self._is_occupied(cell_value):
                    is_available = False
                    break
            
            if is_available:
                available_rooms.append({
                    "category": category,
                    "room": room_number
                })
        
        return available_rooms
    
    def check_room_availability(
        self, 
        room_number: str, 
        date: datetime
    ) -> bool:
        """
        Check if a specific room is available on a specific date.
        
        Args:
            room_number: Room number (e.g., "A-103")
            date: Date to check
        
        Returns:
            True if available, False if occupied
        """
        if not hasattr(self, 'sheet_data') or self.sheet_data is None:
            raise ValueError("Calendar not loaded. Call load_calendar() first.")
        
        check_date = date.date() if isinstance(date, datetime) else date
        
        found_date = self._find_date_in_calendar(check_date, silent=True)
        if not found_date:
            print(f"Date {check_date} not found in calendar")
            return False
        
        col_idx = self.date_column_map[found_date]
        
        # Find the room
        for row_idx in range(self.data_start_row, len(self.sheet_data)):
            row = self.sheet_data[row_idx]
            
            if len(row) < 2:
                continue
            
            room = str(row[1]).strip() if len(row) > 1 and row[1] else ""
            
            if room.lower() == room_number.lower():
                # Found the room, check the cell
                # Check if this cell is part of a merged cell
                actual_row = row_idx
                actual_col = col_idx
                
                if (row_idx, col_idx) in self.merged_cells_map:
                    # This cell is part of a merged range
                    start_row, start_col, end_row, end_col = self.merged_cells_map[(row_idx, col_idx)]
                    # Use the start cell (where the value is)
                    actual_row = start_row
                    actual_col = start_col
                
                # Get cell value from the actual cell (start cell if merged)
                cell_value = ""
                if actual_row < len(self.sheet_data):
                    actual_row_data = self.sheet_data[actual_row]
                    if actual_col < len(actual_row_data):
                        cell_value = str(actual_row_data[actual_col]).strip() if actual_row_data[actual_col] else ""
                
                return not self._is_occupied(cell_value)
        
        print(f"Room {room_number} not found")
        return False
    
    def get_available_categories(
        self, 
        check_in: datetime, 
        check_out: datetime
    ) -> List[str]:
        """
        Get list of categories that have at least one available room.
        
        Args:
            check_in: Check-in date
            check_out: Check-out date
        
        Returns:
            List of category names
        """
        available_rooms = self.get_available_rooms(check_in, check_out)
        categories = set(room["category"] for room in available_rooms)
        return sorted(list(categories))
    
    def show_calendar_info(self):
        """Show information about loaded calendar dates"""
        if not hasattr(self, 'date_column_map') or not self.date_column_map:
            print("Calendar not loaded or no dates found")
            return
        
        dates = sorted(self.date_column_map.keys())
        print(f"\n📅 Calendar Information:")
        print(f"   Total dates: {len(dates)}")
        print(f"   Date range: {dates[0]} to {dates[-1]}")
        print(f"   Years in calendar: {sorted(set(d.year for d in dates))}")
        
        # Show first 10 and last 10 dates
        if len(dates) > 20:
            print(f"\n   First 10 dates: {[str(d) for d in dates[:10]]}")
            print(f"   ... ({len(dates) - 20} more dates) ...")
            print(f"   Last 10 dates: {[str(d) for d in dates[-10:]]}")
        else:
            print(f"\n   All dates: {[str(d) for d in dates]}")
    
    # Backward compatibility methods
    def get_spreadsheet(self, spreadsheet_id):
        """Get spreadsheet metadata (backward compatibility)"""
        try:
            spreadsheet = self.service.spreadsheets().get(
                spreadsheetId=spreadsheet_id
            ).execute()
            return spreadsheet
        except HttpError as error:
            print(f"An error occurred: {error}")
            return None
    
    def read_range(self, spreadsheet_id, range_name):
        """Read data from a specific range (backward compatibility)"""
        try:
            result = self.service.spreadsheets().values().get(
                spreadsheetId=spreadsheet_id,
                range=range_name
            ).execute()
            values = result.get('values', [])
            return values
        except HttpError as error:
            print(f"An error occurred: {error}")
            return None
    
    def read_sheet(self, spreadsheet_id, sheet_name):
        """Read all data from a specific sheet (backward compatibility)"""
        return self.read_range(spreadsheet_id, sheet_name)


# Keep the old class name for backward compatibility
GoogleSheetsParser = HotelBookingParser


def parse_user_date(date_str: str) -> Optional[datetime]:
    """Parse date from user input in various formats"""
    if not date_str:
        return None
    
    date_str = date_str.strip()
    
    # Try common formats
    formats = [
        '%Y-%m-%d',      # 2024-08-01
        '%d.%m.%Y',      # 01.08.2024
        '%d/%m/%Y',      # 01/08/2024
        '%d-%m-%Y',      # 01-08-2024
        '%d.%m',         # 01.08 (assume current year)
        '%d/%m',         # 01/08 (assume current year)
        '%Y/%m/%d',      # 2024/08/01
    ]
    
    for fmt in formats:
        try:
            parsed = datetime.strptime(date_str, fmt)
            # If year not in format, use current year
            if '%Y' not in fmt:
                parsed = parsed.replace(year=datetime.now().year)
            return parsed
        except ValueError:
            continue
    
    return None


def interactive_mode(parser: HotelBookingParser):
    """Interactive mode for querying room availability"""
    print("\n" + "="*60)
    print("🏨 HOTEL ROOM AVAILABILITY CHECKER")
    print("="*60)
    
    # Show calendar info
    parser.show_calendar_info()
    
    print("\nEnter dates to check room availability")
    print("Date formats accepted: YYYY-MM-DD, DD.MM.YYYY, DD/MM/YYYY, DD.MM, DD/MM")
    print("(Press Enter with empty input to exit)")
    print("(Type 'info' to see calendar date range)\n")
    
    while True:
        try:
            # Get check-in date
            check_in_str = input("📅 Check-in date (e.g., 2024-08-01 or 01.08.2024): ").strip()
            if not check_in_str:
                print("Exiting...")
                break
            
            # Special command to show calendar info
            if check_in_str.lower() == 'info':
                parser.show_calendar_info()
                print()
                continue
            
            check_in = parse_user_date(check_in_str)
            if not check_in:
                print("❌ Invalid date format. Please try again.\n")
                continue
            
            # Get check-out date
            check_out_str = input("📅 Check-out date (e.g., 2024-08-05 or 05.08.2024): ").strip()
            if not check_out_str:
                print("Exiting...")
                break
            
            check_out = parse_user_date(check_out_str)
            if not check_out:
                print("❌ Invalid date format. Please try again.\n")
                continue
            
            # Validate date range
            if check_out < check_in:
                print("❌ Check-out date must be on or after check-in date.\n")
                continue
            
            # Optional category filter
            category_filter = input("🏷️  Category filter (optional, press Enter to skip): ").strip()
            if not category_filter:
                category_filter = None
            
            print(f"\n{'='*60}")
            print(f"🔍 Searching for available rooms...")
            print(f"   Check-in:  {check_in.date()}")
            print(f"   Check-out: {check_out.date()}")
            if category_filter:
                print(f"   Category: {category_filter}")
            print(f"{'='*60}")
            
            # Show calendar info if dates not found
            if not parser.date_column_map:
                print("⚠️  No dates found in calendar")
            else:
                cal_min = min(parser.date_column_map.keys())
                cal_max = max(parser.date_column_map.keys())
                if check_in.date() < cal_min or check_out.date() > cal_max:
                    print(f"💡 Calendar range: {cal_min} to {cal_max}")
            print()
            
            # Query available rooms
            available = parser.get_available_rooms(check_in, check_out, category_filter)
            
            # Display results
            if available:
                print(f"✅ Found {len(available)} available room(s):\n")
                
                # Group by category
                by_category = {}
                for room in available:
                    cat = room['category']
                    if cat not in by_category:
                        by_category[cat] = []
                    by_category[cat].append(room['room'])
                
                for category, rooms in sorted(by_category.items()):
                    print(f"  📦 {category}:")
                    for room in sorted(rooms):
                        print(f"     • {room}")
                print()
            else:
                print("❌ No available rooms found for this date range.\n")
            
            # Ask if user wants to continue
            continue_query = input("Search again? (y/n): ").strip().lower()
            if continue_query not in ['y', 'yes', '']:
                break
            
            print()
            
        except KeyboardInterrupt:
            print("\n\nExiting...")
            break
        except Exception as e:
            print(f"\n❌ Error: {e}\n")
            continue


if __name__ == "__main__":
    # Example usage
    parser = HotelBookingParser()
    
    spreadsheet_id = os.getenv('SPREADSHEET_ID')
    sheet_name = os.getenv('SHEET_NAME')  # Optional: specific sheet name
    
    if spreadsheet_id:
        print(f"\nLoading calendar from spreadsheet: {spreadsheet_id}")
        
        # Load the calendar
        if parser.load_calendar(spreadsheet_id, sheet_name):
            # Check if interactive mode is requested via command line argument
            import sys
            if len(sys.argv) > 1 and sys.argv[1] in ['-i', '--interactive', 'interactive']:
                # Interactive mode
                interactive_mode(parser)
            else:
                # Example/demo mode
                print("\n" + "="*60)
                print("💡 TIP: Run with 'python parser.py --interactive' for interactive mode")
                print("="*60)
                
                # Example: Check availability for a date range
                # Adjust dates based on your calendar
                check_in = datetime(2024, 8, 1)
                check_out = datetime(2024, 8, 5)
                
                print(f"\n{'='*60}")
                print(f"Example: Checking availability from {check_in.date()} to {check_out.date()}")
                print(f"{'='*60}")
                
                # Get all available rooms
                available = parser.get_available_rooms(check_in, check_out)
                print(f"\n✅ Available rooms: {len(available)}")
                for room in available:
                    print(f"  - {room['category']}: {room['room']}")
                
                # Get available rooms for specific category
                deluxe_rooms = parser.get_available_rooms(check_in, check_out, category_filter="Deluxe")
                print(f"\n✅ Available Deluxe rooms: {len(deluxe_rooms)}")
                for room in deluxe_rooms:
                    print(f"  - {room['room']}")
                
                # Check specific room
                print(f"\n{'='*60}")
                test_room = "A-202"
                test_date = datetime(2024, 8, 1)
                is_free = parser.check_room_availability(test_room, test_date)
                print(f"Room {test_room} available on {test_date.date()}: {'✅ Yes' if is_free else '❌ No'}")
                
                # Get categories with availability
                categories = parser.get_available_categories(check_in, check_out)
                print(f"\n✅ Categories with availability: {categories}")
                
                # Offer interactive mode
                print(f"\n{'='*60}")
                try:
                    start_interactive = input("\nWould you like to enter custom dates? (y/n): ").strip().lower()
                    if start_interactive in ['y', 'yes']:
                        print()
                        interactive_mode(parser)
                except KeyboardInterrupt:
                    print("\nExiting...")
        else:
            print("Failed to load calendar")
    else:
        print("SPREADSHEET_ID not found in .env file")
