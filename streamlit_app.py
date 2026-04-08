import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import pandas as pd
from datetime import datetime, timedelta
from typing import Any
import streamlit_cookies_manager as scm
import streamlit.components.v1 as components


# Page config
st.set_page_config(page_title="Form Maintenance", page_icon="🔧", layout="wide")

# Load credentials
@st.cache_resource
def get_gspread_client():
    scopes = [
        'https://www.googleapis.com/auth/spreadsheets',
        'https://www.googleapis.com/auth/drive'
    ]
    creds = Credentials.from_service_account_info(
        st.secrets["gcp_service_account"],
        scopes=scopes
    )
    return gspread.authorize(creds)

def get_cache_key():
    """Generate cache key that changes at 02:00 daily"""
    now = datetime.now()
    if now.hour >= 2:
        # After 02:00 today
        return now.strftime('%Y-%m-%d')
    else:
        # Before 02:00, use yesterday's date
        yesterday = now - timedelta(days=1)
        return yesterday.strftime('%Y-%m-%d')

# Load and cache configs
@st.cache_data(ttl=600)  # 10 minutes
def load_all_configs():
    """Load all configs using batch API call for speed"""
    gc = get_gspread_client()
    spreadsheet = gc.open_by_key(st.secrets["spreadsheet_id"])
    
    # ============================================
    # BATCH READ - Single API call for all sheets
    # ============================================
    # This reduces 4 API calls to 1 = ~60% faster
    
    # Define ranges for all sheets (A:Z to cover all columns, adjust if you have more than Z, but try to keep it tight for performance)
    # Need to be updated when adding new columns more than Z, but this is more robust than hardcoding exact columns and allows for some growth without code changes

    ranges = [
        f"{st.secrets['sheets']['dependent_config']}!A:Z",
        f"{st.secrets['sheets']['independent_config']}!A:Z",
        f"{st.secrets['sheets']['work_orders']}!A:Z"
    ]
    
    # Batch get values
    result = spreadsheet.values_batch_get(ranges)
    
    # ============================================
    # Parse sheet data helper function
    # ============================================
    
    def parse_sheet_data(values):
        """Convert sheet values to list of dicts"""
        if not values or len(values) < 2:
            return []
        
        headers = values[0]
        rows = []
        
        for row in values[1:]:
            # Pad row with empty strings if shorter than headers
            padded_row = row + [''] * (len(headers) - len(row))
            row_dict = dict(zip(headers, padded_row))
            rows.append(row_dict)
        
        return rows
    
    # ============================================
    # Parse each sheet's data
    # ============================================
    
    value_ranges = result.get('valueRanges', [])
    
    # Dependent Dropdown Config
    dep_data = parse_sheet_data(value_ranges[0].get('values', []))
    
    # Independent Dropdown Config
    indep_data = parse_sheet_data(value_ranges[1].get('values', []))
    
    # Work Orders
    wo_data = parse_sheet_data(value_ranges[2].get('values', []))
    
    # ============================================
    # Filter work orders (last 28 days)
    # ============================================
    
    cutoff = datetime.now() - timedelta(days=365)
    recent_wo = []
    
    for wo in wo_data:
        try:
            timestamp_str = wo.get('Timestamp', '')
            if timestamp_str:
                ts = datetime.strptime(timestamp_str, '%d/%m/%Y %H:%M:%S')
                if ts >= cutoff:
                    recent_wo.append(wo)
        except Exception as e:
            # Skip malformed dates
            continue
    
    return {
        'dependent': dep_data,
        'independent': indep_data,
        'work_orders': recent_wo
    }

# Initialize session state
def init_session_state():
    if 'authenticated' not in st.session_state:
        st.session_state.authenticated = False
    if 'username' not in st.session_state:
        st.session_state.username = None
    if 'step' not in st.session_state:
        st.session_state.step = 1
    if 'basic_info' not in st.session_state:
        st.session_state.basic_info = {}
    if 'equipment_list' not in st.session_state:
        st.session_state.equipment_list = []
    if 'editing_index' not in st.session_state:
        st.session_state.editing_index = None
    if 'step_2_substep' not in st.session_state:  
        st.session_state.step_2_substep = 1
    if 'step_2_draft' not in st.session_state:
        st.session_state.step_2_draft = {}

# Authentication
def check_authentication(cookies):
    if not st.session_state.authenticated:
        st.title("🔧 Form Maintenance")
        st.subheader("Login")
        
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            
            col_login, col_remember = st.columns([3, 1])
            with col_login:
                login_btn = st.button("Login", use_container_width=True)
            with col_remember:
                remember_me = st.checkbox("Remember")
            
            if login_btn:
                if username in st.secrets["users"]:
                    if password == st.secrets["users"][username]:
                        st.session_state.authenticated = True
                        st.session_state.username = username
                        
                        # Save to cookie if "Remember me" checked
                        if remember_me:
                            cookies['username'] = username
                            cookies.save()
                        
                        st.rerun()
                    else:
                        st.error("Invalid password")
                else:
                    st.error("Invalid username")
        
        st.stop()
# Step 1: Basic Information
def show_step_1(wo_options,department, shifts, garis_produksi, pic_med, pic_eid):
    st.header("📝 Step 1: Basic Information")
    
    # Show previous input from session state if exists
    # Check if basic_info exists and has data
    has_saved_data = bool(st.session_state.basic_info)
    
    # Extract saved values (or use defaults if nothing saved)
    if has_saved_data:
        saved_wo_label = st.session_state.basic_info.get('work_order_label', '')
        saved_department = st.session_state.basic_info.get('department', '')
        saved_shift = st.session_state.basic_info.get('shift', '')
        saved_garis = st.session_state.basic_info.get('garis_produksi', '')
        saved_pic_m = st.session_state.basic_info.get('pic_med', '')
        saved_pic_e = st.session_state.basic_info.get('pic_eid', '')
        
        # Convert date strings back to date objects
        # Saved as: "18/02/2026" → Need: date(2026, 2, 18)
        try:
            saved_tanggal = datetime.strptime(
                st.session_state.basic_info['tanggal'], 
                '%d/%m/%Y'
            ).date()
        except:
            saved_tanggal = datetime.now().date()
        
        try:
            saved_tanggal_mulai = datetime.strptime(
                st.session_state.basic_info['tanggal_mulai'], 
                '%d/%m/%Y'
            ).date()
        except:
            saved_tanggal_mulai = datetime.now().date()
        
        try:
            saved_tanggal_selesai = datetime.strptime(
                st.session_state.basic_info['tanggal_selesai'], 
                '%d/%m/%Y'
            ).date()
        except:
            saved_tanggal_selesai = datetime.now().date()
        
        # Convert time strings back to time objects
        # Saved as: "08:30:00" → Need: time(8, 30, 0)
        try:
            saved_waktu_mulai = datetime.strptime(
                st.session_state.basic_info['waktu_mulai'], 
                '%H:%M:%S'
            ).time()
        except:
            saved_waktu_mulai = None
        
        try:
            saved_waktu_selesai = datetime.strptime(
                st.session_state.basic_info['waktu_selesai'], 
                '%H:%M:%S'
            ).time()
        except:
            saved_waktu_selesai = None
    else:
        # First time filling Step 1 - use default values
        saved_wo_label = ''
        saved_department = ''
        saved_shift = ''
        saved_garis = ''
        saved_pic_m = ''
        saved_pic_e = ''
        saved_tanggal = datetime.now().date()
        saved_tanggal_mulai = datetime.now().date()
        saved_tanggal_selesai = datetime.now().date()
        saved_waktu_mulai = None
        saved_waktu_selesai = None
    
    # ============================================
    # STEP B: Calculate dropdown indices (Garis Produksi is moved underneath WO to get default from WO first)
    # ============================================
    # Streamlit selectbox uses index (position in list) to show default
    # If saved value exists in options, find its position
    # If not, use index 0 (empty option)
        configs = load_all_configs()
        # Extract dropdown options
        indep_df = pd.DataFrame(configs['independent'])
        shifts = sorted([str(x) for x in indep_df['Shift'].dropna().unique()])
        garis_produksi = sorted(indep_df['Garis Produksi'].dropna().unique().tolist())
        department = sorted(indep_df['Department'].dropna().unique().tolist())
        pic_med = sorted(indep_df['PIC MED'].dropna().unique().tolist())
        pic_eid = sorted(indep_df['PIC EID'].dropna().unique().tolist())
    
    
    # Shift index
    shift_list = [""] + shifts
    if saved_shift and saved_shift in shift_list:
        shift_index = shift_list.index(saved_shift)
    else:
        shift_index = 0
    
    # Department index
    department_list = [""] + department 
    if saved_department and saved_department in department_list: 
        department_index = department_list.index(saved_department)
    else:
        department_index = 0
    
    # PIC indices
    pic_med_list = [""] + pic_med
    if saved_pic_m and saved_pic_m in pic_med_list: #type: ignore
        pic_med_index = pic_med_list.index(saved_pic_m)
    else:
        pic_med_index = 0
    
    pic_eid_list = [""] + pic_eid
    if saved_pic_e and saved_pic_e in pic_eid_list: #type: ignore
        pic_eid_index = pic_eid_list.index(saved_pic_e)
    else:
        pic_eid_index = 0
    
    # PICs - use saved values
    st.subheader("PIC")
    col1, col2 = st.columns(2)
    with col1:
        department = st.selectbox(
                    "Department *", 
                    options=department_list, 
                    index=department_index  # <-- Shows saved PIC
            )
    if department and department != "":
        with col2:
            if department == "EID":
                pic = st.selectbox(
                    "PIC EID*",
                    options = pic_eid_list,
                    index = pic_eid_index # <-- Shows saved PIC
                    )
                pic_eid = pic
            elif department == "MED":
                pic = st.selectbox(
                    "PIC MED*",
                    options = pic_med_list,
                    index = pic_med_index # <-- Shows saved PIC
                )
                pic_med = pic
            else:
                st.warning("PIC options are only available for EID and MED departments. Please select one of these departments to choose PIC.")
                pic = None
    # ============================================
    # Step C: Render form with saved values as defaults
    # ============================================
    # Work Order index
    # Filtering The Work Order 
    # Date filter
    wo_df = pd.DataFrame.from_dict(wo_options, orient="index")
    wo_df["Timestamp"] = pd.to_datetime(wo_df["Timestamp"], format="%d/%m/%Y %H:%M:%S")
    col1,col2,col3= st.columns (3)
    with col1:
        start_date = st.date_input(
            "WO setelah:",
            value = pd.Timestamp(datetime.now() - timedelta(7))
            )
    with col2:
        end_date = st.date_input(
            "WO sebelum:",
            value = pd.Timestamp(datetime.now())
        )
    start_date_cutoff, end_date_cutoff = pd.Timestamp(start_date), pd.Timestamp(end_date)
    filtered_wo_df = wo_df[(wo_df['Timestamp'] >= start_date_cutoff) & 
                           (wo_df['Timestamp'] <= end_date_cutoff)]
    # Priority filter
    priority_list = ['','0','1','2','3','4']
    with col3:
        chosen_priority = st.selectbox('Filter Prioritas',
                                options = priority_list)
    #st.write(filtered_wo_df['Prioritas'][0][0])
    if chosen_priority != '' or chosen_priority != False:
        filtered_wo_df = filtered_wo_df[(filtered_wo_df['Prioritas'].str.startswith(chosen_priority))]
    
    if department in ['EID', 'MED']:
        filtered_wo_df = filtered_wo_df[filtered_wo_df[f'{department} Approval'] != 'YES']
    filtered_wo_dict = filtered_wo_df.to_dict(orient = 'index')
    wo_list = [""] + list(filtered_wo_dict.keys())
    
    #st.write(wo_options)
    if saved_wo_label and saved_wo_label in wo_list: #type: ignore
        wo_index = wo_list.index(saved_wo_label)
    else:
        wo_index = 0
        # Work Order - use calculated index based on saved value
    #st.write(wo_options)
    wo_label = st.selectbox(
        "Work Order *",
        options=wo_list,
        index=wo_index,  # <-- This makes it show saved value
        disabled = False if department in ['EID', 'MED'] else True, # Disable if department not selected or not EID/MED
        #help="Select work order from last 28 days"
    )
    
        # Display WO details
    if wo_label and wo_label != "":
        wo_data = wo_options[wo_label]
        st.info(f"**PM:** {wo_data.get('PM', 'N/A')}  \n**Request:** {wo_data.get('Request', 'N/A')}")
        st.info(wo_data.get('Prioritas', 'N/A')) #<- this makes it show the WO priority

    # Garis Produksi index -> moved here to get the default from WO value first
    garis_list = [""] + garis_produksi
    if saved_garis and saved_garis in garis_list:
        garis_index = garis_list.index(saved_garis)
    else:
        try:
            garis_index = garis_list.index(f'PM_{wo_options[wo_label]["PM"]}')  # Try to default to PM value from WO, else empty
        except KeyError:
            garis_index = 0
    #st.divider()
    
    #st.divider()
    with st.form("step1_form"):
        # Date and Shift - use saved values
        st.subheader("📅 Date and Shift")
        col1, col2, col3 = st.columns(3)
        with col1:
            tanggal = st.date_input(
                "Tanggal *",
                value=saved_tanggal,  # <-- Shows saved date
                format="DD/MM/YYYY"
            )
        with col2:
            shift = st.selectbox(
                "Shift *", 
                options=shift_list, 
                index=shift_index  # <-- Shows saved shift
            )
        
        with col3: # Garis Produksi - use saved value
            garis = st.selectbox(
                "Garis Produksi *", 
                options=garis_list, 
                index=garis_index  # <-- Shows saved garis produksi
            )
        
        #st.divider()
        
        # Problem dates/times - use saved values
        st.subheader("⏰ Problem Timeline")
        
        col1, col2 = st.columns(2)
        with col1:
            tanggal_mulai = st.date_input(
                "Tanggal Mulai *",
                value=saved_tanggal_mulai,  # <-- Shows saved date
                format="DD/MM/YYYY"
            )
        with col2:
            waktu_mulai = st.time_input(
                "Waktu Mulai Masalah *",
                value=saved_waktu_mulai,  # <-- Shows saved time (or None)
                step=60
            )
        
        col1, col2 = st.columns(2)
        with col1:
            tanggal_selesai = st.date_input(
                "Tanggal Selesai *",
                value=saved_tanggal_selesai,  # <-- Shows saved date
                format="DD/MM/YYYY"
            )
        with col2:
            waktu_selesai = st.time_input(
                "Waktu Selesai Masalah *",
                value=saved_waktu_selesai,  # <-- Shows saved time (or None)
                step=60
            )
        
        st.divider()
        

        
        # Submit button
        submitted = st.form_submit_button("Next ➡️", use_container_width=True)

    
        

        
        # ============================================
        # STEP D: Validation and saving (same as before)
        # ============================================
        
        if submitted:
            # Validation
            errors = []
            
            if not wo_label or wo_label == "":
                errors.append("Work Order is required")
            if not department or department == "":
                errors.append("Department is required")
            if not shift or shift == "":
                errors.append("Shift is required")
            if not garis or garis == "":
                errors.append("Garis Produksi is required")
            if waktu_mulai is None:
                errors.append("Waktu Mulai Masalah is required")
            if waktu_selesai is None:
                errors.append("Waktu Selesai Masalah is required")
            if not pic or pic == "": #type: ignore
                errors.append("PIC is required")
            
            # Check negative duration
            if waktu_mulai and waktu_selesai:
                start_dt = datetime.combine(tanggal_mulai, waktu_mulai)
                end_dt = datetime.combine(tanggal_selesai, waktu_selesai)
                
                if end_dt <= start_dt:
                    errors.append("Waktu Selesai must be after Waktu Mulai (negative duration not allowed)")
            
            if errors:
                for error in errors:
                    st.error(error)
            else:
                # ============================================
                # STEP E: Save to session state
                # ============================================
                # Save both string format (for writing to sheet)
                # AND the label/object (for reconstructing form defaults)
                
                st.session_state.basic_info = {
                    # For writing to Google Sheets (string format)
                    'work_order': wo_options[wo_label]['Work Order'],
                    'tanggal': tanggal.strftime('%d/%m/%Y'),
                    'shift': shift,
                    'garis_produksi': garis,
                    'tanggal_mulai': tanggal_mulai.strftime('%d/%m/%Y'),
                    'waktu_mulai': waktu_mulai.strftime('%H:%M:%S'), #type: ignore
                    'tanggal_selesai': tanggal_selesai.strftime('%d/%m/%Y'),
                    'waktu_selesai': waktu_selesai.strftime('%H:%M:%S'), #type: ignore
                    'department': department, #type: ignore
                    'pic': pic, #type: ignore
                    'pic_med': pic if department == 'MED' else '', #type: ignore
                    'pic_eid': pic if department == 'EID' else '', #type: ignore
                    
                    
                    # For reconstructing form defaults (labels/objects)
                    'work_order_label': wo_label,  # NEW: Save dropdown label
                }
                
                st.session_state.step = 2
                st.success("✅ Basic info saved! Moving to Step 2...")
                st.rerun()



# Step 2: Equipment Details with Edit Functionality

def show_step_2_form(configs, cookies):
    import json
    import re
    """Step 2 Substep 1: Equipment Form"""

    components.html(f"""
    <script>
        const container = window.parent.document.querySelector('section.stMain');
        if (container) container.scrollTo(0, 0);
    </script>
""", height=0)
    st.header("🔧 Step 2: Equipment Details")
    
    # Show basic info summary
    with st.expander("📋 View Basic Information"):
        st.json(st.session_state.basic_info)
    
    # ============================================
    # Extract dropdown options
    # ============================================
    
    dep_df = pd.DataFrame(configs['dependent'])
    indep_df = pd.DataFrame(configs['independent'])
    
    jenis_tindakan_list = sorted([str(x) for x in indep_df['Jenis Tindakan'].dropna().unique()])
    alasan_kegagalan_list = sorted([str(x) for x in indep_df['Alasan Kegagalan'].dropna().unique()])
    jenis_maintenance_list = sorted([str(x) for x in indep_df['Jenis Maintenance'].dropna().unique()])
    mesin_mati_list = sorted([str(x) for x in indep_df['Mesin Mati?'].dropna().unique()])
    beres_list = sorted([str(x) for x in indep_df['Beres?'].dropna().unique()])
    durasi_solusi_list = sorted([str(x) for x in indep_df['Durasi Solusi'].dropna().unique()])
    
    # ============================================
    # Check if editing mode
    # ============================================
    
    is_editing = st.session_state.editing_index is not None
    
    if is_editing:
        editing_eq = st.session_state.equipment_list[st.session_state.editing_index]
        st.info(f"✏️ Editing Equipment #{st.session_state.editing_index + 1}")

    # Resolving default values for every field
    # When NOT editing: pull defaults from step_2_draft
    #   - draft.get('field', '') returns '' if field not yet saved
    #   - This is exactly what Step 1 does with basic_info
    # When editing: pull defaults from the equipment being edited
    #   - This preserves the existing editing behavior unchanged
    if not is_editing:
            draft = st.session_state.step_2_draft

            equipment_id_default      = draft.get('equipment_id_trouble', '')
            location_id_default       = draft.get('location_id', '')
            area_default              = draft.get('area', '')
            sub_area_default          = draft.get('sub_area', '')
            bagian_default            = draft.get('bagian', '')
            sub_bagian_default        = draft.get('sub_bagian', '')
            jenis_tindakan_default    = draft.get('jenis_tindakan', '')
            deskripsi_tindakan_default = draft.get('deskripsi_tindakan', '')
            alasan_kegagalan_default  = draft.get('alasan_kegagalan', '')
            deskripsi_alasan_default  = draft.get('deskripsi_alasan', '')
            jenis_maintenance_default = draft.get('jenis_maintenance', '')
            mesin_mati_default        = draft.get('mesin_mati', '')
            loss_kapasitas_default    = draft.get('loss_kapasitas', None)
            lama_loss_time_default    = draft.get('lama_loss_time', None)
            beres_default             = draft.get('beres', '')
            durasi_solusi_default     = draft.get('durasi_solusi', '')

    else:
            editing_eq = st.session_state.equipment_list[st.session_state.editing_index]
            # Editing mode: read from the saved equipment entry
            equipment_id_default      = editing_eq['equipment_id_trouble']
            location_id_default       = editing_eq['location_id']
            area_default              = editing_eq['area']
            sub_area_default          = editing_eq['sub_area']
            bagian_default            = editing_eq.get('bagian', '')
            sub_bagian_default        = editing_eq.get('sub_bagian', '')
            jenis_tindakan_default    = editing_eq['jenis_tindakan']
            deskripsi_tindakan_default = editing_eq['deskripsi_tindakan']
            alasan_kegagalan_default  = editing_eq['alasan_kegagalan']
            deskripsi_alasan_default  = editing_eq['deskripsi_alasan']
            jenis_maintenance_default = editing_eq['jenis_maintenance']
            mesin_mati_default        = editing_eq['mesin_mati']
            loss_kapasitas_default    = editing_eq['loss_kapasitas'] if editing_eq['loss_kapasitas'] != "" else None
            lama_loss_time_default    = editing_eq['lama_loss_time'] if editing_eq['lama_loss_time'] != "" else None
            beres_default             = editing_eq['beres']
            durasi_solusi_default     = editing_eq.get('durasi_solusi', '')

    # ============================================
    # Equipment summary with Edit/Delete
    # ============================================
    
    if st.session_state.equipment_list:
        st.subheader("✅ Equipment Added:")
        
        for idx, eq in enumerate(st.session_state.equipment_list):
            sub_bagian_display = eq.get('sub_bagian', '') or '(empty)'
            bagian_display = eq.get('bagian', '') or '(empty)'
            
            col1, col2, col3 = st.columns([6, 1, 1])
            with col1:
                if is_editing and idx == st.session_state.editing_index:
                    st.warning(f"**{idx+1}.** {eq['area']} → {eq['sub_area']} → {bagian_display} → {sub_bagian_display} *(Editing)*")
                else:
                    st.success(f"**{idx+1}.** {eq['area']} → {eq['sub_area']} → {bagian_display} → {sub_bagian_display}")
            with col2:
                edit_disabled = is_editing and idx == st.session_state.editing_index
                if st.button("✏️", key=f"edit_{idx}", disabled=edit_disabled, help="Edit"):
                    st.session_state.editing_index = idx
                    st.rerun()
            with col3:
                if st.button("🗑️", key=f"delete_{idx}", disabled=is_editing, help="Delete"):
                    st.session_state.equipment_list.pop(idx)
                    st.session_state.editing_index = None
                    st.success(f"Equipment #{idx+1} deleted")
                    st.rerun()
        
        st.divider()
    
    # ============================================
    # Equipment form
    # ============================================
    
    st.subheader("🔧 Equipment Information")
    equipment_id_trouble = st.text_input(
            "Equipment ID yang bermasalah (Optional)", 
            value=equipment_id_default,
            max_chars=34,
            help="Format: AAA.BB.CC.DD.E.FFF.GG.HHHH.IIII.JJ (34 characters)"
        )
    equipment_id_replacement = st.text_input(
            "Equipment ID pengganti (Optional)", 
            value=equipment_id_default,
            max_chars=34,
            help="Format: AAA.BB.CC.DD.E.FFF.GG.HHHH.IIII.JJ (34 characters)"
        )
    location_id = st.text_input(
        "Location_ID (Optional)",
        value = location_id_default,
        max_chars = 29,
        help = "Format: AAA.BB.CC.DD.EE.FFFF.GGGG.HHH (29 characters)"
    )
    #st.write(str(location_id).split('.')[5])
    # Area
    areas = sorted(dep_df['Area'].dropna().unique().tolist())
    area_options = [""] + areas
    #st.write(areas.index(area_default))
    if is_editing and editing_eq['area'] in areas: #type: ignore
        area_index = areas.index(editing_eq['area']) + 1 #type: ignore
    elif location_id:
        parsed_area_code = str(location_id).split('.')[4] #The area code from location ID
        named_area = dep_df[dep_df['Area_Code'] == parsed_area_code]['Area'].values[0] #type: ignore
        area_index = areas.index(named_area) + 1
    else:
        area_index = 0
    area_selectbox_key = f"area_select_{location_id}" if location_id else "area_select"
    area = st.selectbox("Area *", options=area_options, index=area_index, key=area_selectbox_key)
    
    # Sub Area
    if area and area != "":
        sub_areas = sorted(dep_df[dep_df['Area'] == area]['Sub Area'].dropna().unique().tolist())
        sub_area_options = [""] + sub_areas
        
        if is_editing and editing_eq['sub_area'] in sub_areas: #type: ignore
            sub_area_index = sub_areas.index(editing_eq['sub_area']) + 1 #type: ignore
        elif location_id:
            try:
                parsed_sub_area_code = str(location_id).split('.')[5] #The sub area code from location ID
                named_sub_area = dep_df[dep_df['Sub Area_Code'] == parsed_sub_area_code]['Sub Area'].values[0] #type: ignore
                sub_area_index = sub_areas.index(named_sub_area) + 1
            except Exception as E:
                st.info('Location ID tidak cocok dengan pilihan area.')
                sub_area_index = 0
        else:
            sub_area_index = 0
        sub_area_selectbox_key = f"sub_area_select_{location_id}" if location_id else "sub_area_select"
        sub_area = st.selectbox("Sub Area *", options=sub_area_options, index=sub_area_index, key=sub_area_selectbox_key)
    else:
        sub_area = st.selectbox("Sub Area *", options=[], disabled=True)
        sub_area = None
    # ======================================
    # Bagian
    # ======================================
    if area and area != "" and sub_area and sub_area != "":
        filtered = dep_df[(dep_df['Area'] == area) & (dep_df['Sub Area'] == sub_area)]
        bagian_values = filtered['Bagian'].tolist()
        bagian_options = [""]
        for val in bagian_values:
            if pd.isna(val) or val == "":
                if "" not in bagian_options:
                    bagian_options.append("")
            else:
                if val not in bagian_options:
                    bagian_options.append(val)
        
        non_empty = sorted([x for x in bagian_options if x != ""])
        bagian_options = [""] + non_empty
        
        if is_editing:
            edit_bagian = editing_eq.get('bagian', '') #type: ignore
            if edit_bagian in bagian_options:
                bagian_index = bagian_options.index(edit_bagian)
            else:
                bagian_index = 0
        elif location_id:
            try:
                parsed_bagian_code = str(location_id).split('.')[6] #The bagian code from location ID
                named_bagian = dep_df[dep_df["Bagian_Code"] == parsed_bagian_code]["Bagian"].values[0] #type: ignore
                bagian_index = bagian_options.index(named_bagian)
            except:
                st.info('Location ID tidak cocok dengan pilihan sub area')
                bagian_index = 0
        #elif bagian_default and area == area_default and sub_area == sub_area_default: 
            #bagian_index = bagian_options.index(bagian_default)
        else:
            bagian_index = 0
        
        bagian = st.selectbox("Bagian", options=bagian_options, index=bagian_index, key="bagian_select")
    else:
        bagian = st.selectbox("Bagian", options=[], disabled=True)
        bagian = None
    
    # Sub Bagian
    if area and area != "" and sub_area and sub_area != "" and bagian is not None:
        if bagian == "":
            filtered = dep_df[
                (dep_df['Area'] == area) & 
                (dep_df['Sub Area'] == sub_area) & 
                ((dep_df['Bagian'].isna()) | (dep_df['Bagian'] == ""))
            ]
        else:
            filtered = dep_df[
                (dep_df['Area'] == area) & 
                (dep_df['Sub Area'] == sub_area) & 
                (dep_df['Bagian'] == bagian)
            ]
        
        sub_bagian_values = filtered['Sub Bagian'].tolist()
        sub_bagian_options = [""]
        for val in sub_bagian_values:
            if not pd.isna(val) and val != "" and val not in sub_bagian_options:
                sub_bagian_options.append(val)
        
        sub_bagian_options = [""] + sorted([x for x in sub_bagian_options if x != ""])
        
        if is_editing:
            edit_sub_bagian = editing_eq.get('sub_bagian', '') #type: ignore
            if edit_sub_bagian in sub_bagian_options:
                sub_bagian_index = sub_bagian_options.index(edit_sub_bagian)
            else:
                sub_bagian_index = 0
        elif sub_bagian_default and area == area_default and sub_area == sub_area_default and bagian == bagian_default:
            sub_bagian_index = sub_bagian_options.index(sub_bagian_default)
        else:
            sub_bagian_index = 0
        
        sub_bagian = st.selectbox("Sub Bagian (Optional)", options=sub_bagian_options, index=sub_bagian_index, key="sub_bagian_select")
    else:
        sub_bagian = st.selectbox("Sub Bagian (Optional)", options=[], disabled=True)
        sub_bagian = None
    
    st.divider()
    
    # Tindakan
    st.subheader("🛠️ Action Details")
    
    jenis_tindakan_options = [""] + jenis_tindakan_list
    if is_editing and editing_eq['jenis_tindakan'] in jenis_tindakan_list: #type: ignore
        jt_index = jenis_tindakan_list.index(editing_eq['jenis_tindakan']) + 1 #type: ignore
    else:
        jt_index = 0
    jenis_tindakan_val = st.selectbox("Jenis Tindakan *", 
                                      options=jenis_tindakan_options, 
                                      index=jt_index)
    
    deskripsi_tindakan_default = editing_eq['deskripsi_tindakan'] if is_editing else "" #type: ignore
    deskripsi_tindakan = st.text_area("Deskripsi Tindakan *", 
                                      value=deskripsi_tindakan_default)
    
    # Kegagalan
    st.subheader("⚠️ Failure Reason")
    
    alasan_kegagalan_options = [""] + alasan_kegagalan_list
    if is_editing and editing_eq['alasan_kegagalan'] in alasan_kegagalan_list: #type: ignore
        ak_index = alasan_kegagalan_list.index(editing_eq['alasan_kegagalan']) + 1 #type: ignore
    else:
        ak_index = 0
    alasan_kegagalan_val = st.selectbox("Alasan Kegagalan *", 
                                        options=alasan_kegagalan_options, 
                                        index=ak_index)
    
    deskripsi_alasan_default = editing_eq['deskripsi_alasan'] if is_editing else ""   #type: ignore
    deskripsi_alasan = st.text_area("Deskripsi Alasan *",
                                     value=deskripsi_alasan_default,
                                       height=100)
    
    st.divider()
    
    # Technical details
    col1, col2 = st.columns(2)
    with col1:
        jenis_maintenance_options = [""] + jenis_maintenance_list
        if is_editing and editing_eq['jenis_maintenance'] in jenis_maintenance_list: #type: ignore
            jm_index = jenis_maintenance_list.index(editing_eq['jenis_maintenance']) + 1 #type: ignore
        else:
            jm_index = 0
        jenis_maintenance_val = st.selectbox("Jenis Maintenance *",
                                            options=jenis_maintenance_options, 
                                            index=jm_index)
        

        
        mesin_mati_options = [""] + mesin_mati_list
        if is_editing and editing_eq['mesin_mati'] in mesin_mati_list: #type: ignore
            mm_index = mesin_mati_list.index(editing_eq['mesin_mati']) + 1 #type: ignore
        else:
            mm_index = 0
        mesin_mati_val = st.selectbox("Mesin Mati? *", 
                                      options=mesin_mati_options, 
                                      index=mm_index)
    
    with col2:
        loss_kapasitas_default = editing_eq['loss_kapasitas'] if is_editing and editing_eq['loss_kapasitas'] != "" else None #type: ignore
        loss_kapasitas = st.number_input(
            "Loss Kapasitas (KG) (Optional)", 
            min_value=0.0, 
            value=loss_kapasitas_default, 
            step=0.1,
            format="%.1f"
        )
        
        lama_loss_time_default = editing_eq['lama_loss_time'] if is_editing and editing_eq['lama_loss_time'] != "" else None #type: ignore
        lama_loss_time = st.number_input(
            "Lama Loss Time (Menit) (Optional)", 
            min_value=0.0, 
            value=lama_loss_time_default, 
            step=0.1,
            format="%.1f"
        )
    
    # Status
    col1, col2 = st.columns(2)
    with col1:
        beres_options = [""] + beres_list
        if is_editing and editing_eq['beres'] in beres_list: #type: ignore
            b_index = beres_list.index(editing_eq['beres']) + 1 #type: ignore
        else:
            b_index = 0
        beres_val = st.selectbox("Beres? *", 
                                 options=beres_options, 
                                 index=b_index)
    with col2:
        durasi_solusi_options = [""] + durasi_solusi_list
        if is_editing and editing_eq['durasi_solusi'] in durasi_solusi_list: #type: ignore
            ds_index = durasi_solusi_list.index(editing_eq['durasi_solusi']) + 1 #type: ignore
        else:
            ds_index = 0
        durasi_solusi_val = st.selectbox("Durasi Solusi (Diisi jika 'Beres? = Sementara')", 
                                         options=durasi_solusi_options, 
                                         index=ds_index)
    
    st.divider()
    
    # Saving draft after all widgets are rendered
    if not is_editing:

        # Collect every widget's current value into a single dict
        new_draft = {
            'equipment_id_trouble':           equipment_id_trouble           if equipment_id_trouble           else '',
            'equipment_id_replacement':       equipment_id_replacement       if equipment_id_replacement       else '',
            'location_id':            location_id            if location_id            else '',
            'area':                   area                   if area                   else '',
            'sub_area':               sub_area               if sub_area               else '',
            'bagian':                 bagian                 if bagian                 else '',
            'sub_bagian':             sub_bagian             if sub_bagian             else '',
            'jenis_tindakan':         jenis_tindakan_val     if jenis_tindakan_val     else '',
            'deskripsi_tindakan':     deskripsi_tindakan     if deskripsi_tindakan     else '',
            'alasan_kegagalan':       alasan_kegagalan_val   if alasan_kegagalan_val   else '',
            'deskripsi_alasan':       deskripsi_alasan       if deskripsi_alasan       else '',
            'jenis_maintenance':      jenis_maintenance_val  if jenis_maintenance_val  else '',
            'mesin_mati':             mesin_mati_val         if mesin_mati_val         else '',
            'loss_kapasitas':         loss_kapasitas,   # None or float — preserved as-is
            'lama_loss_time':         lama_loss_time,   # None or float — preserved as-is
            'beres':                  beres_val              if beres_val              else '',
            'durasi_solusi':          durasi_solusi_val      if durasi_solusi_val      else '',
        }

        # Only save when the draft actually changed
        # This prevents a cookie write + potential extra rerun on every single render
        if new_draft != st.session_state.step_2_draft:

            # 1. Update session state (persists across step navigation within a session)
            st.session_state.step_2_draft = new_draft

            # 2. Serialize to JSON and write to cookie (persists across full page refresh)
            # json.dumps converts the Python dict to a JSON string for cookie storage
            cookies['step_2_draft'] = json.dumps(new_draft)
            cookies.save()
    # ============================================
    # Buttons - SEPARATED LOGIC
    # ============================================
    
    if is_editing:
        # EDITING MODE
        col1, col2 = st.columns(2)
        with col1:
            if st.button("❌ Cancel Edit", use_container_width=True):
                st.session_state.s2_editing_loaded = None
                st.session_state.editing_index = None
                st.rerun()
        with col2:
            if st.button("💾 Update Equipment", use_container_width=True, type="primary"):
                # Validate and update
                errors = []
                
                if not area or area == "":
                    errors.append("❌ Area is required")
                if not sub_area or sub_area == "":
                    errors.append("❌ Sub Area is required")
                if not jenis_tindakan_val or jenis_tindakan_val == "":
                    errors.append("❌ Jenis Tindakan is required")
                if not deskripsi_tindakan or deskripsi_tindakan.strip() == "":
                    errors.append("❌ Deskripsi Tindakan is required")
                if not alasan_kegagalan_val or alasan_kegagalan_val == "":
                    errors.append("❌ Alasan Kegagalan is required")
                if not deskripsi_alasan or deskripsi_alasan.strip() == "":
                    errors.append("❌ Deskripsi Alasan is required")
                if not jenis_maintenance_val or jenis_maintenance_val == "":
                    errors.append("❌ Jenis Maintenance is required")
                if not mesin_mati_val or mesin_mati_val == "":
                    errors.append("❌ Mesin Mati? is required")
                if not beres_val or beres_val == "":
                    errors.append("❌ Beres? is required")
                
                if equipment_id_trouble and equipment_id_trouble.strip() != "":
                    import re
                    pattern = r'^\d{3}\.\d{2}\.[A-Z]{2}\.\d{2}\.[A-Z]\.\d{3}\.\d{2}\.[A-Z]{4}\.[A-Z]{4}\.\d{2}$'
                    if not re.match(pattern, equipment_id_trouble):
                        errors.append("❌ Equipment ID format invalid. Harus: AAA.BB.CC.DD.E.FFF.GG.HHHH.IIII.JJ")

                if equipment_id_replacement and equipment_id_replacement.strip() != "":
                    import re
                    pattern = r'^\d{3}\.\d{2}\.[A-Z]{2}\.\d{2}\.[A-Z]\.\d{3}\.\d{2}\.[A-Z]{4}\.[A-Z]{4}\.\d{2}$'
                    if not re.match(pattern, equipment_id_replacement):
                        errors.append("❌ Replacement Equipment ID format invalid. Harus: AAA.BB.CC.DD.E.FFF.GG.HHHH.IIII.JJ")
                    if equipment_id_trouble and equipment_id_trouble.strip() != "" and equipment_id_replacement and equipment_id_replacement.strip() != "":
                        if equipment_id_trouble.strip() == equipment_id_replacement.strip():
                            errors.append("❌ Equipment ID yang bermasalah dan pengganti tidak boleh sama")

                if location_id and location_id.strip() != "":
                    import re
                    pattern = r'^\d{3}\.\d{2}\.[A-Z]{2}\.\d{2}\.[A-Z]{2}\.[A-Z]{4}\.[A-Z]{4}\.\d{3}$'
                    if not re.match(pattern, location_id):
                        errors.append("❌ Location ID format invalid. Harus: AAA.BB.CC.DD.EE.FFFF.GGGG.HHH")

                if errors:
                    for error in errors:
                        st.error(error)
                else:
                    equipment = {
                        'area': area,
                        'sub_area': sub_area,
                        'bagian': bagian if bagian else "",
                        'sub_bagian': sub_bagian if sub_bagian else "",
                        'jenis_tindakan': jenis_tindakan_val,
                        'deskripsi_tindakan': deskripsi_tindakan,
                        'alasan_kegagalan': alasan_kegagalan_val,
                        'deskripsi_alasan': deskripsi_alasan,
                        'jenis_maintenance': jenis_maintenance_val,
                        'equipment_id_trouble': equipment_id_trouble if equipment_id_trouble else "",
                        'equipment_id_replacement': equipment_id_replacement if equipment_id_replacement else "",
                        'location_id': location_id if location_id else "",
                        'mesin_mati': mesin_mati_val,
                        'loss_kapasitas': loss_kapasitas if loss_kapasitas is not None else "",
                        'lama_loss_time': lama_loss_time if lama_loss_time is not None else "",
                        'beres': beres_val,
                        'durasi_solusi': durasi_solusi_val if durasi_solusi_val else ""
                    }
                    
                    st.session_state.equipment_list[st.session_state.editing_index] = equipment
                    st.session_state.editing_index = None
                    st.success("✅ Equipment updated!")
                    st.rerun()
    
    else:
        # ADDING MODE
        col1, col2 = st.columns(2)
        with col1:
            if st.button("➕ Tambah Equipment", use_container_width=True):
                # Validate and add
                errors = []
                
                if not area or area == "":
                    errors.append("❌ Area is required")
                if not sub_area or sub_area == "":
                    errors.append("❌ Sub Area is required")
                if not jenis_tindakan_val or jenis_tindakan_val == "":
                    errors.append("❌ Jenis Tindakan is required")
                if not deskripsi_tindakan or deskripsi_tindakan.strip() == "":
                    errors.append("❌ Deskripsi Tindakan is required")
                if not alasan_kegagalan_val or alasan_kegagalan_val == "":
                    errors.append("❌ Alasan Kegagalan is required")
                if not deskripsi_alasan or deskripsi_alasan.strip() == "":
                    errors.append("❌ Deskripsi Alasan is required")
                if not jenis_maintenance_val or jenis_maintenance_val == "":
                    errors.append("❌ Jenis Maintenance is required")
                if not mesin_mati_val or mesin_mati_val == "":
                    errors.append("❌ Mesin Mati? is required")
                if not beres_val or beres_val == "":
                    errors.append("❌ Beres? is required")
                
                if equipment_id_trouble and equipment_id_trouble.strip() != "":
                    import re 
                    pattern = r'^\d{3}\.\d{2}\.[A-Z]{2}\.\d{2}\.[A-Z]\.\d{3}\.\d{2}\.[A-Z]{4}\.[A-Z]{4}\.\d{2}$'
                    if not re.match(pattern, equipment_id_trouble):
                        errors.append("❌ Equipment ID format invalid. Harus: AAA.BB.CC.DD.E.FFF.GG.HHHH.IIII.JJ")
                
                if equipment_id_replacement and equipment_id_replacement.strip() != "":
                    import re 
                    pattern = r'^\d{3}\.\d{2}\.[A-Z]{2}\.\d{2}\.[A-Z]\.\d{3}\.\d{2}\.[A-Z]{4}\.[A-Z]{4}\.\d{2}$'
                    if not re.match(pattern, equipment_id_replacement):
                        errors.append("❌ Replacement Equipment ID format invalid. Harus: AAA.BB.CC.DD.E.FFF.GG.HHHH.IIII.JJ")
                    if equipment_id_trouble and equipment_id_trouble.strip() != "" and equipment_id_replacement and equipment_id_replacement.strip() != "":
                        if equipment_id_trouble.strip() == equipment_id_replacement.strip():
                            errors.append("❌ Equipment ID yang bermasalah dan pengganti tidak boleh sama")

                if location_id and location_id.strip() != "":
                    import re
                    pattern = r'^\d{3}\.\d{2}\.[A-Z]{2}\.\d{2}\.[A-Z]{2}\.[A-Z]{4}\.[A-Z]{4}\.\d{3}$'
                    if not re.match(pattern, location_id):
                        errors.append("❌ Location ID format invalid. Must be: AAA.BB.CC.DD.EE.FFFF.GGGG.HHH")

                if errors:
                    for error in errors:
                        st.error(error)
                else:
                    equipment = {
                        'area': area,
                        'sub_area': sub_area,
                        'bagian': bagian if bagian else "",
                        'sub_bagian': sub_bagian if sub_bagian else "",
                        'jenis_tindakan': jenis_tindakan_val,
                        'deskripsi_tindakan': deskripsi_tindakan,
                        'alasan_kegagalan': alasan_kegagalan_val,
                        'deskripsi_alasan': deskripsi_alasan,
                        'jenis_maintenance': jenis_maintenance_val,
                        'equipment_id_trouble': equipment_id_trouble if equipment_id_trouble else "",
                        'equipment_id_replacement': equipment_id_replacement if equipment_id_replacement else "",
                        'location_id': location_id if location_id else "",
                        'mesin_mati': mesin_mati_val,
                        'loss_kapasitas': loss_kapasitas if loss_kapasitas is not None else "",
                        'lama_loss_time': lama_loss_time if lama_loss_time is not None else "",
                        'beres': beres_val,
                        'durasi_solusi': durasi_solusi_val if durasi_solusi_val else ""
                    }
                    
                    st.session_state.equipment_list.append(equipment)
                    st.success(f"✅ Equipment #{len(st.session_state.equipment_list)} added!")
                    st.rerun()
        
        with col2:
            # Submit All button - NO validation, just check if list not empty
            submit_disabled = len(st.session_state.equipment_list) == 0
            if st.button("✅ Submit All", use_container_width=True, type="primary", disabled=submit_disabled):
                # Go to confirmation substep
                st.session_state.step_2_substep = 2
                st.rerun()
        
        if submit_disabled:
            st.caption("⚠️ Add at least one equipment before submitting")
    
    # Back button
    st.divider()
    col1, col2, col3 = st.columns([1, 2, 1])
    with col1:
        if st.button("⬅️ Back to Step 1", use_container_width=True, disabled=is_editing):
            st.session_state.step = 1
            st.rerun()
        
        if is_editing:
            st.caption("⚠️ Cancel edit to go back")

def show_step_2_confirmation(cookies):
    import json
    """Step 2 Substep 2: Confirmation Page"""
    import time

    components.html(f"""
    <script>
        // {time.time()}
        const container = window.parent.document.querySelector('section.stMain');
        if (container) container.scrollTo(0, 0);
    </script>
""", height=0)

    st.header("📋 Review & Confirm Submission")
    st.warning("⚠️ **Please review your submission carefully before confirming**")
    
    # Display summary
    display_submission_summary(st.session_state.basic_info, st.session_state.equipment_list)
    
    st.divider()
    
    # Confirmation buttons
    col1, col2, col3 = st.columns([2, 1, 1])
    
    with col2:
        if st.button("⬅️ Back to Edit", use_container_width=True):
            # Return to form substep
            st.session_state.step_2_substep = 1
            st.rerun()
    
    with col3:
        if st.button("✅ Confirm & Submit", use_container_width=True, type="primary"):
            # Actual submission
            with st.spinner("📤 Submitting to Google Sheets..."):
                import time
                success, message = submit_to_google_sheet(
                    st.session_state.basic_info,
                    st.session_state.equipment_list
                )
            
            if success:
                st.success(f"✅ {message}")
                st.balloons()
                
                # Clear all session data
                st.session_state.basic_info = {}
                st.session_state.equipment_list = []
                st.session_state.editing_index = None
                st.session_state.step_2_substep = 1  # Reset substep
                st.session_state.step = 1
                

                st.session_state.step_2_draft = {}

                # Clear the cookie by writing an empty JSON object
                # We don't delete the cookie key entirely — we just write {} to it
                # so that the restore logic in main() finds it empty and skips restore
                cookies['step_2_draft'] = json.dumps({})
                cookies.save()

                st.cache_data.clear()
                
                st.info("🔄 Returning to Step 1...")
                time.sleep(2)
                st.rerun()
            else:
                st.error(f"❌ Submission failed: {message}")
                st.session_state.step_2_substep = 1  # Return to form on error

def show_step_2(configs, cookies):
    """Router for Step 2 substeps"""
    
    if st.session_state.step_2_substep == 1:
        # Substep 1: Equipment form
        show_step_2_form(configs, cookies)
    elif st.session_state.step_2_substep == 2:
        # Substep 2: Confirmation
        show_step_2_confirmation(cookies)

def display_submission_summary(basic_info, equipment_list):
    """Display scrollable summary of data to be submitted"""
    
    st.subheader("📋 Submission Summary")
    st.write(f"**Total Equipment:** {len(equipment_list)} item(s)")
    
    # ============================================
    # Basic Information Section
    # ============================================
    
    with st.expander("📄 Basic Information", expanded=False):
        col1, col2 = st.columns(2)
        
        with col1:
            st.write("**Work Order:**", basic_info['work_order'])
            st.write("**Tanggal:**", basic_info['tanggal'])
            st.write("**Shift:**", basic_info['shift'])
            st.write("**Garis Produksi:**", basic_info['garis_produksi'])
        
        with col2:
            st.write("**Mulai:**", f"{basic_info['tanggal_mulai']} {basic_info['waktu_mulai']}")
            st.write("**Selesai:**", f"{basic_info['tanggal_selesai']} {basic_info['waktu_selesai']}")
            st.write("**Department:**", basic_info['department'])
            st.write("**PIC:**", basic_info['pic'])
    
    st.divider()
    
    # ============================================
    # Equipment List Section (Scrollable)
    # ============================================
    
    # Custom CSS for better styling
    st.markdown("""
    <style>
    /* Scrollbar styling */
    div[data-testid="stExpander"]::-webkit-scrollbar {
        width: 8px;
    }
    div[data-testid="stExpander"]::-webkit-scrollbar-track {
        background: #f1f1f1;
        border-radius: 10px;
    }
    div[data-testid="stExpander"]::-webkit-scrollbar-thumb {
        background: #888;
        border-radius: 10px;
    }
    div[data-testid="stExpander"]::-webkit-scrollbar-thumb:hover {
        background: #555;
    }
    </style>
    """, unsafe_allow_html=True)
    
    if len(equipment_list) > 3:
        st.info(f"📜 Scroll down to review all {len(equipment_list)} equipment")
    
    # Display each equipment
    for idx, eq in enumerate(equipment_list, 1):
        with st.expander(f"🔧 Equipment #{idx}: {eq['area']} → {eq['sub_area']} → {eq.get('bagian', '(empty)')}", expanded=True):
            
            # Location details
            st.write("**📍 Location:**")
            col1, col2 = st.columns(2)
            with col1:
                st.write("• Area:", eq['area'])
                st.write("• Sub Area:", eq['sub_area'])
            with col2:
                st.write("• Bagian:", eq.get('bagian', '(empty)'))
                st.write("• Sub Bagian:", eq.get('sub_bagian', '(empty)'))
            
            st.divider()
            
            # Action details
            st.write("**🛠️ Action:**")
            st.write("• Jenis Tindakan:", eq['jenis_tindakan'])
            st.write("• Deskripsi:", eq['deskripsi_tindakan'])
            
            st.divider()
            
            # Failure details
            st.write("**⚠️ Failure:**")
            st.write("• Alasan:", eq['alasan_kegagalan'])
            st.write("• Deskripsi:", eq['deskripsi_alasan'])
            
            st.divider()
            
            # Technical details
            col1, col2 = st.columns([2, 1])
            with col1:
                st.write("**🔧 Technical:**")
                st.write("• Jenis Maintenance:", eq['jenis_maintenance'])
                st.write("• Equipment ID Trouble:", eq['equipment_id_trouble'] or "(empty)")
                st.write("• Equipment ID Replacement:", eq['equipment_id_replacement'] or "(empty)")
                st.write("• Location ID:", eq['location_id'] or "(empty)")
                st.write("• Mesin Mati?:", eq['mesin_mati'])
            
            with col2:
                st.write("**📊 Metrics:**")
                loss_kap = eq['loss_kapasitas'] if eq['loss_kapasitas'] != "" else "N/A"
                loss_time = eq['lama_loss_time'] if eq['lama_loss_time'] != "" else "N/A"
                st.write("• Loss Kapasitas:", f"{loss_kap} KG" if loss_kap != "N/A" else "N/A")
                st.write("• Lama Loss Time:", f"{loss_time} min" if loss_time != "N/A" else "N/A")
            
            st.divider()
            
            # Status
            col1, col2 = st.columns(2)
            with col1:
                st.write("• Beres?:", eq['beres'])
            with col2:
                durasi_sol = eq['durasi_solusi'] if eq['durasi_solusi'] else "(empty)"
                st.write("• Durasi Solusi:", durasi_sol)

def submit_to_google_sheet(basic_info, equipment_list):
    """Write all equipment to Google Sheet"""
    
    try:
        gc = get_gspread_client()
        spreadsheet = gc.open_by_key(st.secrets["spreadsheet_id"])
        data_sheet = spreadsheet.worksheet(st.secrets["sheets"]["data_sheet"])
        
        # Calculate Durasi Aksi
        start_dt = datetime.strptime(
            f"{basic_info['tanggal_mulai']} {basic_info['waktu_mulai']}", 
            '%d/%m/%Y %H:%M:%S'
        )
        end_dt = datetime.strptime(
            f"{basic_info['tanggal_selesai']} {basic_info['waktu_selesai']}", 
            '%d/%m/%Y %H:%M:%S'
        )
        durasi_aksi = (end_dt - start_dt).total_seconds() / 60
        
        # ============================================
        # FIX: Find actual next empty row (robust)
        # ============================================
        
        all_values = data_sheet.get_all_values()
        next_row = 2  # Start from row 2 (after header)
        
        # Find first empty row
        for idx, row in enumerate(all_values[1:], start=2):
            if not row[0] or not str(row[0]).strip():
                next_row = idx
                break
        else:
            # No empty row found, append after last
            next_row = len(all_values) + 1
        
        # Safety check
        if next_row < 2:
            next_row = 2
        
        # Prepare rows
        from typing import Any
        rows_to_add: list[list[Any]] = []
        
        for equipment in equipment_list:
            row = [
                basic_info['work_order'],
                basic_info['tanggal'],
                basic_info['department'],
                basic_info['shift'],
                basic_info['garis_produksi'],
                equipment['area'],
                equipment['sub_area'],
                equipment['bagian'],
                equipment['sub_bagian'],
                basic_info['tanggal_mulai'],
                basic_info['waktu_mulai'],
                basic_info['tanggal_selesai'],
                basic_info['waktu_selesai'],
                equipment['jenis_tindakan'],
                equipment['deskripsi_tindakan'],
                equipment['alasan_kegagalan'],
                equipment['deskripsi_alasan'],
                equipment['jenis_maintenance'],
                equipment['location_id'],
                equipment['equipment_id_trouble'],
                equipment['equipment_id_replacement'],
                equipment['mesin_mati'],
                durasi_aksi,
                equipment['loss_kapasitas'],
                equipment['lama_loss_time'],
                equipment['beres'],
                equipment['durasi_solusi'],
                basic_info['pic']
            ]
            rows_to_add.append(row)
        
        # Write to specific range
        start_row = next_row
        end_row = next_row + len(rows_to_add) - 1
        range_notation = f"A{start_row}:AB{end_row}"
        
        data_sheet.update(range_notation, rows_to_add) #type: ignore
        
        return True, f"Successfully submitted {len(equipment_list)} equipment(s) to row {start_row}"
        
    except Exception as e:
        import traceback
        return False, f"Error: {str(e)}\n{traceback.format_exc()}"
#Main App
def main():
    import json # For serializing or deserializing the draft
    init_session_state()
    cookies = scm.CookieManager()

    if not cookies.ready():
        st.stop()

    # Check for saved login
    if not st.session_state.authenticated:
        saved_user = cookies.get('username')
        if saved_user:
            # Auto-login from cookie
            st.session_state.authenticated = True
            st.session_state.username = saved_user

    # To restore step 2 draft from cookie
    if not st.session_state.step_2_draft:
        raw_draft = cookies.get('step_2_draft')
        if raw_draft:
            try:
                st.session_state.step_2_draft = json.loads(raw_draft)
            except Exception:
                st.session_state.step_2_draft = {}
    check_authentication(cookies)
    
    # Header
    col1, col2, col3 = st.columns([4, 1, 1])
    with col1:
        st.title("🔧 Form Maintenance")
    with col2:
        if st.button("🔄 Refresh Data"):
            st.cache_data.clear()
            st.success("Data refreshed!")
            st.rerun()
    with col3:
        if st.button("🚪 Logout"):
            st.session_state.authenticated = False
            st.session_state.username = None
            #Clearing cookies
            cookies['username'] = ''
            cookies.save()
            st.rerun()
    
    st.write(f"👤 Logged in as: **{st.session_state.username}**")
    st.divider()
    
    # Load configs
    try:
        configs = load_all_configs()
        
        # Extract dropdown options
        indep_df = pd.DataFrame(configs['independent'])
        shifts = sorted([str(x) for x in indep_df['Shift'].dropna().unique()])
        department = sorted(indep_df['Department'].dropna().unique().tolist())
        garis_produksi = sorted(indep_df['Garis Produksi'].dropna().unique().tolist())
        pic_med = sorted(indep_df['PIC MED'].dropna().unique().tolist())
        pic_eid = sorted(indep_df['PIC EID'].dropna().unique().tolist())
        
        # Work orders with labels
        wo_options = {}
        for wo in configs['work_orders']:
            wo_num = wo['Work Order']
            if wo_num[2:4] == "KO":
                label = f"{wo_num} (Korektif)"
                wo_options[label] = wo
            elif wo_num[2:4] == "VE":
                label = f"{wo_num} (Preventif)"
                wo_options[label] = wo
            elif wo_num[2:4] == "IM":
                label = f"{wo_num} (Improvement)"
                wo_options[label] = wo
            elif wo_num[2:4] == "DI":
                label = f"{wo_num} (Prediktif Intuitif)"
                wo_options[label] = wo
            elif wo_num[2:4] == "DH":
                label = f"{wo_num} (Prediktif Hybrid)"
                wo_options[label] = wo
            elif wo_num[2:4] == "DS":
                label = f"{wo_num} (Prediktif Statistik)"
                wo_options[label] = wo
            else:
                st.write(f"⚠️ Unknown Work Order type for {wo_num}")

        # Show current step
        if st.session_state.step == 1:
            show_step_1(wo_options, department, shifts, garis_produksi, pic_med, pic_eid) #type: ignore
        elif st.session_state.step == 2:
            show_step_2(configs, cookies)
        
    except Exception as e:
        st.error(f"Error loading configs: {e}")
        import traceback
        st.code(traceback.format_exc())

if __name__ == "__main__":
    main()