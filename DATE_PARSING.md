# Date Parsing Configuration

## Overview

The parser supports two modes for reading dates from the Google Sheet:

1. **Manual Mode** (recommended): Specify the starting cell and date
2. **Auto-detect Mode**: Automatically finds the date header row

## Manual Mode

In manual mode, you specify:
- The starting cell where dates begin (e.g., `C7`)
- The start date (e.g., `24.11.2025`)

The parser will then go right from that cell and create sequential dates (24.11.2025, 25.11.2025, 26.11.2025, etc.).

### Configuration via Environment Variables

Add to your `.env` file:

```bash
DATE_START_CELL=C7
DATE_START=24.11.2025
```

### Configuration via API

When calling `/calendar/load`:

```json
{
  "spreadsheet_id": "your_spreadsheet_id",
  "sheet_name": "Sheet1",
  "date_start_cell": "C7",
  "date_start": "24.11.2025"
}
```

### How It Works

1. The parser reads the cell specified by `DATE_START_CELL` (e.g., C7)
2. If `DATE_START` is provided, it uses that date
3. If `DATE_START` is not provided, it tries to parse the date from the cell itself
4. Starting from that cell, it goes right column by column
5. For each column, it creates a sequential date (current_date + 1 day)
6. It skips columns that contain day abbreviations (пн, вт, ср, etc.)
7. It continues until it reaches the end of the row or 730 dates (~2 years)

### Example

If you set:
- `DATE_START_CELL=C7`
- `DATE_START=24.11.2025`

The parser will create:
- Column C (index 2): 2025-11-24
- Column D (index 3): 2025-11-25
- Column E (index 4): 2025-11-26
- Column F (index 5): 2025-11-27
- ... and so on

## Auto-detect Mode

If `DATE_START_CELL` is not set, the parser will automatically:
1. Search for rows containing month names (январь, февраль, etc.)
2. Find the row with day numbers (1, 2, 3, etc.)
3. Parse dates from the detected header row

This mode is more complex and may not work correctly if your sheet structure is non-standard.

## Cell Reference Format

The `DATE_START_CELL` should be in Excel format:
- `C7` - Column C, Row 7
- `AA10` - Column AA, Row 10
- `Z1` - Column Z, Row 1

## Date Format

The `DATE_START` should be in one of these formats:
- `24.11.2025` (DD.MM.YYYY) - recommended
- `24/11/2025` (DD/MM/YYYY)
- `2025-11-24` (YYYY-MM-DD)

## Troubleshooting

### "Could not determine start date"
- Make sure `DATE_START` is set in `.env` or provided via API
- Or ensure the cell specified by `DATE_START_CELL` contains a valid date

### Dates don't match
- Check that `DATE_START_CELL` points to the correct cell
- Verify that `DATE_START` is correct
- Remember: dates are sequential, so if you start at 24.11.2025, the next column will be 25.11.2025

### Too many/few dates
- The parser stops after 730 dates (2 years) by default
- Check that your sheet has enough columns for the date range you need

