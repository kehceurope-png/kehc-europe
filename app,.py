import streamlit as st
import gspread
import json
import pandas as pd
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
from datetime import datetime
import time

# ------------------------------------------------------------------
# 1. 설정 및 연결
# ------------------------------------------------------------------
st.set_page_config(page_title="유럽직할지방회 행정 시스템", layout="wide")

# (A) 구글 시트 및 드라이브 연결 함수
@st.cache_resource
def get_google_services():
    # Secrets 처리 (Plan A/B 모두 대응)
    if "gcp_service_account" in st.secrets:
        key_dict = dict(st.secrets["gcp_service_account"])
        if "\\n" in key_dict["private_key"]:
            key_dict["private_key"] = key_dict["private_key"].replace("\\n", "\n")
    else:
        key_dict = json.loads(st.secrets["service_account_json"], strict=False)

    scopes = [
        "https://www.googleapis.com/auth/spreadsheets", 
        "https://www.googleapis.com/auth/drive"
    ]
    creds = Credentials.from_service_account_info(key_dict, scopes=scopes)
    
    # 1. 시트 연결
    client = gspread.authorize(creds)
    # 2. 드라이브 연결
    drive_service = build('drive', 'v3', credentials=creds)
    
    return client, drive_service

# (B) 구글 드라이브 업로드 함수
def upload_to_drive(file_obj, filename, folder_id, drive_service):
    file_metadata = {
        'name': filename,
        'parents': [folder_id]
    }
    media = MediaIoBaseUpload(file_obj, mimetype=file_obj.type)
    file = drive_service.files().create(
        body=file_metadata,
        media_body=media,
        fields='id, webViewLink'
    ).execute()
    return file.get('webViewLink')

# (C) 구글 시트 기록 함수 (파일명 변경됨: 지방회_시스템)
def log_document(date, title, writer, url, status):
    client, _ = get_google_services()
    sh = client.open("지방회_시스템") 
    worksheet = sh.worksheet("documents")
    worksheet.append_row([date, title, writer, url, status])

# (D) 결재 승인 함수 (파일명 변경됨: 지방회_시스템)
def approve_document(row_idx):
    client, _ = get_google_services()
    sh = client.open("지방회_시스템")
    worksheet = sh.worksheet("documents")
    worksheet.update_cell(row_idx + 2, 5, "승인완료") 

# ------------------------------------------------------------------
# 2. 로그인 및 메인 로직
# ------------------------------------------------------------------
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False

if not st.session_state.logged_in:
    st.header("🔒 유럽직할지방회 임원 로그인")
    with st.form("login"):
        uid = st.text_input("아이디")
        upw = st.text_input("비밀번호", type="password")
        if st.form_submit_button("로그인"):
            try:
                client, _ = get_google_services()
                sh = client.open("지방회_시스템") # 파일명 변경됨
                users = sh.worksheet("users").get_all_records()
                
                found = False
                for u in users:
                    if str(u['username']) == str(uid) and str(u['password']) == str(upw):
                        st.session_state.logged_in = True
                        st.session_state.user = u
                        found = True
                        st.rerun()
                if not found:
