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

@st.cache_resource
def get_google_services():
    # Secrets 처리
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
    
    client = gspread.authorize(creds)
    drive_service = build('drive', 'v3', credentials=creds)
    
    return client, drive_service

def upload_to_drive(file_obj, filename, folder_id, drive_service):
    file_metadata = {'name': filename, 'parents': [folder_id]}
    media = MediaIoBaseUpload(file_obj, mimetype=file_obj.type)
    file = drive_service.files().create(
        body=file_metadata, media_body=media, fields='id, webViewLink'
    ).execute()
    return file.get('webViewLink')

def log_document(date, title, writer, url, status):
    client, _ = get_google_services()
    sh = client.open("지방회_시스템") 
    worksheet = sh.worksheet("documents")
    worksheet.append_row([date, title, writer, url, status])

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
        submit_btn = st.form_submit_button("로그인")
        
        if submit_btn:
            try:
                client, _ = get_google_services()
                sh = client.open("지방회_시스템")
                users = sh.worksheet("users").get_all_records()
                
                found = False
                for u in users:
                    # 문자열로 변환하여 비교
                    if str(u['username']) == str(uid) and str(u['password']) == str(upw):
                        st.session_state.logged_in = True
                        st.session_state.user = u
                        found = True
                        st.rerun()
                
                if not found:
                    st.error("아이디 또는 비밀번호를 확인하세요.")
                    
            except Exception as e:
                st.error(f"로그인 오류: {e}")

else:
    # ------------------------------------------------------------------
    # 3. 업무 화면
    # ------------------------------------------------------------------
    user = st.session_state.user
    
    with st.sidebar:
        st.write(f"👤 **{user['name']}** ({user['role']})")
        menu = st.radio("메뉴 선택", ["대시보드", "문서관리", "회계관리(준비중)"])
        if st.button("로그아웃"):
            st.session_state.logged_in = False
            st.rerun()

    st.title("🇪🇺 유럽직할지방회 행정 시스템")

    if menu == "대시보드":
        st.info("👋 환영합니다. 왼쪽 메뉴에서 업무를 선택해주세요.")

    elif menu == "문서관리":
        st.subheader("📄 문서 제출 및 결재")
        
        try:
            client, drive_service = get_google_services()
            sh = client.open("지방회_시스템")
            doc_sheet = sh.worksheet("documents")
            docs = doc_sheet.get_all_records()
            df = pd.DataFrame(docs)

            if not df.empty:
                st.dataframe(df[['date', 'title', 'writer', 'status', 'file_url']])
                
                if user['role'] == 'admin':
                    st.write("---")
                    st.write("### 👑 결재 대기 문서")
                    pending_docs = df[df['status'] == '대기']
                    
                    if not pending_docs.empty:
                        for idx, row in pending_docs.iterrows():
                            col1, col2, col3 = st.columns([3, 1, 1])
                            with col1:
                                st.write(f"**{row['title']}** (작성: {row['writer']})")
                            with col2:
                                st.link_button("문서보기", row['file_url'])
                            with col3:
                                if st.button("승인", key=f"btn_{idx}"):
                                    approve_document(idx)
                                    st.success("승인되었습니다!")
                                    time.sleep(1)
                                    st.rerun()
                    else:
                        st.info("결재할 문서가 없습니다.")
            else:
                st.info("등록된 문서가 없습니다.")

            if user['role'] in ['secretary', 'admin']: 
                st.write("---")
                st.write("### 📤 새 문서 등록")
                with st.form("upload_doc"):
                    date = st.date_input("날짜", datetime.today())
                    title = st.text_input("문서 제목")
                    uploaded_file = st.file_uploader("파일 선택")
                    
                    submit_doc = st.form_submit_button("제출하기")
                    
                    if submit_doc:
                        if not title or not uploaded_file:
                            st.warning("제목과 파일을 입력하세요.")
                        else:
                            with st.spinner("업로드 중..."):
                                try:
                                    folder_id = st.secrets["drive_folder_id"]
                                    file_url = upload_to_drive(uploaded_file, title, folder_id, drive_service)
                                    log_document(str(date), title, user['name'], file_url, "대기")
                                    st.success("제출 완료!")
                                    time.sleep(1)
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"오류: {e}")
        except Exception as e:
            st.error(f"데이터를 불러오는 중 오류가 발생했습니다: {e}")

    elif menu == "회계관리(준비중)":
        st.warning("🚧 현재 개발 중입니다.")
