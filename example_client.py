"""Example client usage for the Hotel Booking Parser API"""
import requests
from datetime import datetime, timedelta

BASE_URL = "http://localhost:8000"


def example_usage():
    """Example usage of the API"""
    
    # 1. Check health
    print("1. Checking API health...")
    response = requests.get(f"{BASE_URL}/health")
    print(f"   Status: {response.json()}\n")
    
    # 2. Load calendar
    print("2. Loading calendar...")
    spreadsheet_id = input("Enter spreadsheet ID: ").strip()
    sheet_name = input("Enter sheet name (or press Enter to skip): ").strip() or None
    
    load_data = {
        "spreadsheet_id": spreadsheet_id
    }
    if sheet_name:
        load_data["sheet_name"] = sheet_name
    
    response = requests.post(f"{BASE_URL}/calendar/load", json=load_data)
    result = response.json()
    print(f"   Result: {result['message']}")
    if result['success']:
        print(f"   Calendar info: {result.get('calendar_info')}\n")
    else:
        print("   Failed to load calendar. Exiting.")
        return
    
    # 3. Get calendar info
    print("3. Getting calendar information...")
    response = requests.get(f"{BASE_URL}/calendar/info")
    info = response.json()
    print(f"   Total dates: {info['total_dates']}")
    print(f"   Date range: {info['date_range']['min_date']} to {info['date_range']['max_date']}")
    print(f"   Years: {info['years']}\n")
    
    # 4. Get available rooms
    print("4. Getting available rooms...")
    check_in = input("Enter check-in date (YYYY-MM-DD): ").strip()
    check_out = input("Enter check-out date (YYYY-MM-DD): ").strip()
    category_filter = input("Enter category filter (optional, press Enter to skip): ").strip() or None
    
    request_data = {
        "check_in": check_in,
        "check_out": check_out
    }
    if category_filter:
        request_data["category_filter"] = category_filter
    
    response = requests.post(f"{BASE_URL}/rooms/available", json=request_data)
    rooms_data = response.json()
    print(f"   Found {rooms_data['count']} available room(s):")
    for room in rooms_data['available_rooms']:
        print(f"     - {room['category']}: {room['room']}")
    print()
    
    # 5. Check specific room
    print("5. Checking specific room availability...")
    room_number = input("Enter room number: ").strip()
    check_date = input("Enter date to check (YYYY-MM-DD): ").strip()
    
    response = requests.post(f"{BASE_URL}/rooms/check", json={
        "room_number": room_number,
        "date": check_date
    })
    check_result = response.json()
    status = "✅ Available" if check_result['available'] else "❌ Occupied"
    print(f"   Room {check_result['room_number']} on {check_result['date']}: {status}\n")
    
    # 6. Get available categories
    print("6. Getting available categories...")
    response = requests.post(f"{BASE_URL}/categories/available", json={
        "check_in": check_in,
        "check_out": check_out
    })
    categories_data = response.json()
    print(f"   Available categories: {', '.join(categories_data['categories'])}\n")


if __name__ == "__main__":
    try:
        example_usage()
    except KeyboardInterrupt:
        print("\n\nExiting...")
    except Exception as e:
        print(f"\nError: {e}")

