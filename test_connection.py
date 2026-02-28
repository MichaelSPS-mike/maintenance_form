import gspread
from google.oauth2.service_account import Credentials
import streamlit as st
from datetime import datetime, timedelta

# Load credentials from secrets
scopes = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive'
]

creds = Credentials.from_service_account_info(
    st.secrets["gcp_service_account"],
    scopes=scopes
)

gc = gspread.authorize(creds)

# Config from secrets
SPREADSHEET_ID = st.secrets["spreadsheet_id"]
SHEET_DEPENDENT = st.secrets["sheets"]["dependent_config"]
SHEET_INDEPENDENT = st.secrets["sheets"]["independent_config"]
SHEET_WORK_ORDERS = st.secrets["sheets"]["work_orders_korektif"]
SHEET_DATA = st.secrets["sheets"]["data_sheet"]

print("🔍 Testing Google Sheets Connection...\n")

try:
    # Open spreadsheet
    spreadsheet = gc.open_by_key(SPREADSHEET_ID)
    print(f"✅ Connected to spreadsheet: {spreadsheet.title}")
    
    # Test 1: Read Dependent Dropdown Config
    print(f"\n📋 Test 1: Reading '{SHEET_DEPENDENT}'...")
    sheet_dep = spreadsheet.worksheet(SHEET_DEPENDENT)
    data_dep = sheet_dep.get_all_records()
    print(f"   ✅ Found {len(data_dep)} rows")
    if data_dep:
        print(f"   Sample: {data_dep[0]}")
    
    # Test 2: Read Independent Dropdown Config
    print(f"\n📋 Test 2: Reading '{SHEET_INDEPENDENT}'...")
    sheet_indep = spreadsheet.worksheet(SHEET_INDEPENDENT)
    data_indep = sheet_indep.get_all_records()
    print(f"   ✅ Found {len(data_indep)} rows")
    if data_indep:
        print(f"   Sample: {data_indep[0]}")
    
    # Test 3: Read Work Orders
    print(f"\n📋 Test 3: Reading '{SHEET_WORK_ORDERS}'...")
    sheet_wo = spreadsheet.worksheet(SHEET_WORK_ORDERS)
    data_wo = sheet_wo.get_all_records()
    print(f"   ✅ Found {len(data_wo)} work orders")
    
    # Filter last 28 days
    cutoff = datetime.now() - timedelta(days=28)
    recent_wo = []
    for wo in data_wo:
        try:
            ts = datetime.strptime(wo['Timestamp'], '%d/%m/%Y %H:%M:%S') #type: ignore
            if ts >= cutoff:
                recent_wo.append(wo)
        except:
            pass
    print(f"   ✅ {len(recent_wo)} work orders in last 28 days")
    if recent_wo:
        print(f"   Sample: {recent_wo[0]['Work Order']} - {recent_wo[0]['Masalah']}")
    
    # Test 4: Write Test Row to Data Sheet
    print(f"\n📋 Test 4: Writing test row to '{SHEET_DATA}'...")
    sheet_data = spreadsheet.worksheet(SHEET_DATA)
    
    test_row = [
        "TEST_WO",  # Work Order
        "01/01/2026",  # Tanggal
        "1",  # Shift
        "TEST_PM",  # Garis Produksi
        "TEST",  # Area
        "TEST",  # Sub Area
        "TEST",  # Bagian
        "",  # Sub Bagian
        "01/01/2026",  # Tanggal Mulai
        "08:00:00",  # Waktu Mulai
        "01/01/2026",  # Tanggal Selesai
        "09:00:00",  # Waktu Selesai
        "Test",  # Jenis Tindakan
        "Connection test",  # Deskripsi Tindakan
        "Test",  # Alasan Kegagalan
        "Testing connection",  # Deskripsi Alasan
        "Test",  # Jenis Maintenance
        "",  # Tag Number
        "Ya",  # Mesin Mati?
        60.0,  # Durasi Aksi
        100.5,  # Loss Kapasitas
        60.0,  # Lama Loss Time
        "Test",  # Beres?
        "",  # Durasi Solusi
        "TestUser",  # PIC Produksi
        "TestUser",  # PIC MED
        "TestUser"  # PIC EID
    ]
    
    sheet_data.append_row(test_row)
    print(f"   ✅ Test row written successfully!")
    print(f"   ⚠️  Please check '{SHEET_DATA}' and DELETE the test row manually")
    
    print("\n" + "="*50)
    print("🎉 ALL TESTS PASSED!")
    print("="*50)
    print("\n✅ Your Google Sheets connection is working perfectly!")
    print("✅ Ready to build the Streamlit app!")
    
except Exception as e:
    print(f"\n❌ ERROR: {e}")
    print("\nTroubleshooting:")
    print("1. Check spreadsheet_id in secrets.toml")
    print("2. Check sheet names match exactly (case-sensitive)")
    print("3. Verify service account has Editor permission")
    print("4. Check credentials in secrets.toml are correct")