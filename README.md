# Google Sheets Hotel Booking Parser - FastAPI Service

A FastAPI-based REST API service for parsing and querying hotel booking calendars from Google Sheets using the Google Sheets API. Automatically detects available rooms for date ranges.

## Features

- ✅ RESTful API with FastAPI
- ✅ Automatic date header detection
- ✅ Room availability checking for date ranges
- ✅ Category-based filtering
- ✅ Handles Russian and English month names
- ✅ Detects occupied cells (guest names, special labels, etc.)
- ✅ Structured JSON responses
- ✅ Interactive API documentation (Swagger UI)
- ✅ OpenAPI schema support

## Setup

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Set up Google Sheets API credentials:
   - Go to [Google Cloud Console](https://console.cloud.google.com/)
   - Create a new project or select an existing one
   - Enable the Google Sheets API
   - Create credentials (Service Account or OAuth2)
   - Download the credentials JSON file
   - **Important**: Share your Google Sheet with the service account email (found in the JSON file)

3. Create a `.env` file:
```bash
# Google Sheets API credentials
GOOGLE_CREDENTIALS_PATH=path/to/your/service-account-key.json
# OR
GOOGLE_CREDENTIALS_JSON={"type": "service_account", ...}

# Optional: Server configuration
HOST=0.0.0.0
PORT=8000

# Optional: Spreadsheet configuration (can also be set via API)
SPREADSHEET_ID=your_spreadsheet_id
SHEET_NAME=Sheet1

# Optional: Date parsing configuration
# Specify the starting cell for dates (e.g., C7 where dates begin)
DATE_START_CELL=C7
# Optional: Specify the start date explicitly (e.g., 24.11.2025)
# If not provided, will try to read from the cell itself
DATE_START=24.11.2025
```

## Running the Service

### Development Mode

```bash
python main.py
```

Or using uvicorn directly:

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Production Mode

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
```

### Docker Deployment

**Prerequisites:**
- Docker and Docker Compose installed

**Quick Start:**

1. Copy environment template:
```bash
cp env.example .env
```

2. Edit `.env` file with your configuration (Google credentials, spreadsheet ID, etc.)

3. Build and start with Docker Compose:
```bash
docker compose up -d --build
```

4. Or use the deployment script:
```bash
chmod +x deploy.sh
./deploy.sh
```

5. View logs:
```bash
docker compose logs -f
```

6. Stop the service:
```bash
docker compose down
```

**For Digital Ocean Droplet deployment**, see [DEPLOYMENT.md](DEPLOYMENT.md) for detailed instructions.

The API will be available at:
- API: http://localhost:8000
- Interactive Docs (Swagger): http://localhost:8000/docs
- Alternative Docs (ReDoc): http://localhost:8000/redoc

## API Endpoints

### Health & Info

- `GET /` - Root endpoint with API information
- `GET /health` - Health check endpoint

### Calendar Management

- `POST /calendar/load` - Load calendar from Google Sheets
  ```json
  {
    "spreadsheet_id": "your_spreadsheet_id",
    "sheet_name": "Sheet1",  // optional
    "date_start_cell": "C7",  // optional: starting cell for dates (e.g., "C7")
    "date_start": "24.11.2025"  // optional: start date (e.g., "24.11.2025")
  }
  ```
  
  **Date Parsing Modes:**
  - **Manual mode**: If `date_start_cell` is provided, the parser will start from that cell and count dates sequentially going right
  - **Auto-detect mode**: If `date_start_cell` is not provided, the parser will automatically detect the date header row

- `GET /calendar/info` - Get information about loaded calendar

### Room Availability

- `POST /rooms/available` - Get available rooms for a date range
  ```json
  {
    "check_in": "2024-08-01",
    "check_out": "2024-08-05",
    "category_filter": "Deluxe"  // optional
  }
  ```

- `POST /rooms/check` - Check if a specific room is available
  ```json
  {
    "room_number": "A-103",
    "date": "2024-08-01"
  }
  ```

### Categories

- `POST /categories/available` - Get categories with available rooms
  ```json
  {
    "check_in": "2024-08-01",
    "check_out": "2024-08-05"
  }
  ```

## Usage Examples

### Using cURL

```bash
# Load calendar
curl -X POST "http://localhost:8000/calendar/load" \
  -H "Content-Type: application/json" \
  -d '{
    "spreadsheet_id": "your_spreadsheet_id",
    "sheet_name": "Sheet1"
  }'

# Get available rooms
curl -X POST "http://localhost:8000/rooms/available" \
  -H "Content-Type: application/json" \
  -d '{
    "check_in": "2024-08-01",
    "check_out": "2024-08-05"
  }'

# Check specific room
curl -X POST "http://localhost:8000/rooms/check" \
  -H "Content-Type: application/json" \
  -d '{
    "room_number": "A-103",
    "date": "2024-08-01"
  }'
```

### Using Python

```python
import requests

BASE_URL = "http://localhost:8000"

# Load calendar
response = requests.post(
    f"{BASE_URL}/calendar/load",
    json={
        "spreadsheet_id": "your_spreadsheet_id",
        "sheet_name": "Sheet1"
    }
)
print(response.json())

# Get available rooms
response = requests.post(
    f"{BASE_URL}/rooms/available",
    json={
        "check_in": "2024-08-01",
        "check_out": "2024-08-05",
        "category_filter": "Deluxe"
    }
)
data = response.json()
print(f"Found {data['count']} available rooms")
for room in data['available_rooms']:
    print(f"  {room['category']}: {room['room']}")
```

### Using JavaScript/TypeScript

```javascript
const BASE_URL = 'http://localhost:8000';

// Load calendar
const loadResponse = await fetch(`${BASE_URL}/calendar/load`, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    spreadsheet_id: 'your_spreadsheet_id',
    sheet_name: 'Sheet1'
  })
});
const loadData = await loadResponse.json();
console.log(loadData);

// Get available rooms
const roomsResponse = await fetch(`${BASE_URL}/rooms/available`, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    check_in: '2024-08-01',
    check_out: '2024-08-05'
  })
});
const roomsData = await roomsResponse.json();
console.log(`Found ${roomsData.count} available rooms`);
```

## API Response Examples

### Available Rooms Response

```json
{
  "available_rooms": [
    {"category": "Deluxe", "room": "A-103"},
    {"category": "Deluxe", "room": "A-202"},
    {"category": "Superior", "room": "B-105"}
  ],
  "count": 3,
  "check_in": "2024-08-01",
  "check_out": "2024-08-05",
  "category_filter": null
}
```

### Calendar Info Response

```json
{
  "total_dates": 365,
  "date_range": {
    "min_date": "2024-01-01",
    "max_date": "2024-12-31"
  },
  "years": [2024],
  "header_row": 10,
  "data_start_row": 11,
  "sample_dates": ["2024-01-01", "2024-01-02", ...]
}
```

## How It Works

1. **Date Detection**: Automatically finds the row containing dates in the sheet
2. **Month Context**: Handles month names (July/August) to correctly parse day numbers
3. **Room Parsing**: Extracts category (Column A) and room number (Column B)
4. **Availability Check**: A room is available if ALL cells in the date range are empty
5. **Occupied Detection**: Detects occupied cells by any text content (guest names, special labels, etc.)

## Sheet Structure Expected

- **Column A**: Room category (e.g., "Deluxe", "Superior")
- **Column B**: Room number (e.g., "A-103", "B-202")
- **Columns C+**: Dates (one column per day)
- **Header rows**: Contain dates (automatically detected)
- **Legend rows**: Automatically skipped

## Environment Variables

- `GOOGLE_CREDENTIALS_PATH`: Path to service account JSON file
- `GOOGLE_CREDENTIALS_JSON`: OAuth2 credentials as JSON string (alternative to file path)
- `HOST`: Server host (default: 0.0.0.0)
- `PORT`: Server port (default: 8000)
- `SPREADSHEET_ID`: Your Google Spreadsheet ID (optional, can be set via API)
- `SHEET_NAME`: Specific sheet name (optional, can be set via API)
- `DATE_START_CELL`: Starting cell for dates (e.g., "C7") - enables manual date parsing mode
- `DATE_START`: Start date in format DD.MM.YYYY (e.g., "24.11.2025") - optional, will try to read from cell if not provided

## Troubleshooting

### Permission Error (403)
Make sure you've shared your Google Sheet with the service account email (found in your credentials JSON file).

### Dates Not Found
- Check that your date headers are in a recognizable format
- Ensure the sheet structure matches the expected format
- Try specifying the sheet name explicitly

### No Available Rooms
- Verify the date range is correct
- Check that rooms exist in the sheet
- Ensure the category filter (if used) matches exactly

### Service Not Starting
- Check that credentials are properly configured in `.env`
- Verify Google Sheets API is enabled in Google Cloud Console
- Check logs for authentication errors

## Development

### Project Structure

```
.
├── app/
│   ├── __init__.py
│   ├── main.py          # FastAPI application
│   ├── models.py        # Pydantic models
│   └── parser.py        # Hotel booking parser
├── main.py              # Entry point
├── requirements.txt     # Dependencies
└── README.md           # This file
```

### Running Tests

```bash
# Install test dependencies
pip install pytest pytest-asyncio httpx

# Run tests
pytest
```

## License

MIT
