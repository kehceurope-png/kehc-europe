import streamlit as st
import gspread
import json
import pandas as pd
import requests
import base64
from google.oauth2.service_account import Credentials
from datetime import datetime
import time

# ------------------------------------------------------------------
# 1. 설정 및 연결
# ------------------------------------------------------------------
st.set_page_config(page_title="유럽직할지방회 행정 시스템", layout="wide")

@st.cache_resource
def get_google_sheet():
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
    return client

# Apps Script를 통한 파일 업로드 함수
def upload_file_via_script(file_obj, filename, folder_id, script_url):
    file_content = file_obj.read()
    file_b64 = base64.b64encode(file_content).decode('utf-8')
    
    payload = {
        'folder_id': folder_id,
        'filename': filename,
        'mimeType': file_obj.type,
        'fileBase64': file_b64
    }
    
    response = requests.post(script_url, json=payload)
    
    if response.status_code == 200:
        result = response.json()
        if result.get('status') == 'success':
            return result.get('fileUrl')
        else:
            raise Exception(f"스크립트 오류: {result.get('message')}")
    else:
        raise Exception(f"통신 오류: {response.text}")

# 기록 함수들
def log_document(date, title, writer, url, status):
    client = get_google_sheet()
    sh = client.open("지방회_시스템") 
    worksheet = sh.worksheet("documents")
    worksheet.append_row([str(date), title, writer, url, status])

def approve_document(row_idx):
    client = get_google_sheet()
    sh = client.open("지방회_시스템")
    worksheet = sh.worksheet("documents")
    worksheet.update_cell(row_idx + 2, 5, "승인완료") 

def log_finance(date, f_type, category, amount, desc, url, status):
    client = get_google_sheet()
    sh = client.open("지방회_시스템")
    worksheet = sh.worksheet("finance")
    worksheet.append_row([str(date), f_type, category, amount, desc, url, status])

def approve_finance(row_idx):
    client = get_google_sheet()
    sh = client.open("지방회_시스템")
    worksheet = sh.worksheet("finance")
    worksheet.update_cell(row_idx + 2, 7, "승인완료")

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
                client = get_google_sheet()
                sh = client.open("지방회_시스템")
                users = sh.worksheet("users").get_all_records()
                
                found = False
                for u in users:
                    if str(u['username']) == str(uid) and str(u['password']) == str(upw):
                        st.session_state.logged_in = True
                        st.session_state.user = u
                        found = True
                        st.rerun()
                if not found:
                    st.error("아이디 또는 비밀번호를 확인하세요.")
            except Exception as e:
                st.error(f"시스템 접속 오류: {e}")

else:
    user = st.session_state.user
    
    with st.sidebar:
        st.write(f"👤 **{user['name']}** ({user['role']})")
        menu = st.radio("메뉴", ["대시보드", "문서관리", "회계관리"])
        if st.button("로그아웃"):
            st.session_state.logged_in = False
            st.rerun()

    st.title("🇪🇺 유럽직할지방회 행정 시스템")

    # [1] 대시보드 (업그레이드 됨)
    if menu == "대시보드":
        st.subheader("📊 한눈에 보는 현황")
        
        try:
            client = get_google_sheet()
            sh = client.open("지방회_시스템")
            
            # 데이터 가져오기 (문서 & 재정)
            doc_data = sh.worksheet("documents").get_all_records()
            fin_data = sh.worksheet("finance").get_all_records()
            
            df_doc = pd.DataFrame(doc_data)
            df_fin = pd.DataFrame(fin_data)
            
            # 1. 문서 대기 건수 계산
            pending_docs = 0
            if not df_doc.empty:
                pending_docs = len(df_doc[df_doc['status'] == '대기'])
                
            # 2. 재정 대기 건수 및 잔액 계산
            pending_fin = 0
            balance = 0
            if not df_fin.empty:
                # 금액 콤마 제거 및 숫자 변환
                df_fin['amount'] = pd.to_numeric(df_fin['amount'].astype(str).str.replace(',', ''), errors='coerce').fillna(0)
                pending_fin = len(df_fin[df_fin['status'] == '대기'])
                
                income = df_fin[df_fin['type'] == '수입']['amount'].sum()
                expense = df_fin[df_fin['type'] == '지출']['amount'].sum()
                balance = income - expense

            # 3. 화면에 카드 형태로 보여주기
            col1, col2, col3 = st.columns(3)
            
            col1.metric("📄 결재 대기 문서", f"{pending_docs}건", 
                        delta="확인 필요" if pending_docs > 0 else "완료",
                        delta_color="inverse" if pending_docs > 0 else "normal")
            
            col2.metric("💰 결재 대기 재정", f"{pending_fin}건",
                        delta="확인 필요" if pending_fin > 0 else "완료",
                        delta_color="inverse" if pending_fin > 0 else "normal")
            
            col3.metric("💶 현재 재정 잔액", f"€ {int(balance):,}")
            
            st.divider()
            
            # 4. 종합 알림 메시지
            total_pending = pending_docs + pending_fin
            
            if total_pending > 0:
                st.warning(f"🔔 현재 총 **{total_pending}건**의 승인 대기 항목이 있습니다. 왼쪽 메뉴에서 확인해주세요.")
            else:
                st.success("✅ 모든 업무가 처리되었습니다. 현재 대기 중인 항목이 없습니다.")
                st.balloons() # 업무가 없을 때 풍선 효과 (재미 요소)

        except Exception as e:
            st.error(f"데이터를 불러오는 중입니다 (또는 오류): {e}")


    # [2] 문서관리
    elif menu == "문서관리":
        st.subheader("📄 문서 제출 및 결재")
        try:
            client = get_google_sheet()
            sh = client.open("지방회_시스템")
            df = pd.DataFrame(sh.worksheet("documents").get_all_records())

            if not df.empty:
                st.dataframe(df[['date', 'title', 'writer', 'status', 'file_url']])
                if user['role'] == 'admin':
                    pending = df[df['status'] == '대기']
                    if not pending.empty:
                        st.write("### 👑 결재 대기")
                        for idx, row in pending.iterrows():
                            c1, c2, c3 = st.columns([3,1,1])
                            with c1: st.write(f"**{row['title']}**")
                            with c2: st.link_button("보기", row['file_url'])
                            with c3:
                                if st.button("승인", key=f"d_{idx}"):
                                    approve_document(idx)
                                    st.success("승인됨")
                                    time.sleep(1)
                                    st.rerun()

            if user['role'] in ['secretary', 'admin']: 
                st.write("---")
                st.write("### 📤 새 문서 등록")
                with st.form("doc_upload"):
                    d_date = st.date_input("날짜", datetime.today())
                    d_title = st.text_input("제목")
                    d_file = st.file_uploader("파일")
                    if st.form_submit_button("제출"):
                        if d_title and d_file:
                            with st.spinner("업로드 중..."):
                                try:
                                    fid = st.secrets["drive_folder_id"]
                                    s_url = st.secrets["upload_script_url"]
                                    url = upload_file_via_script(d_file, d_title, fid, s_url)
                                    log_document(d_date, d_title, user['name'], url, "대기")
                                    st.success("완료!")
                                    time.sleep(1)
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"업로드 오류: {e}")
                        else:
                            st.warning("파일과 제목을 입력하세요.")
        except Exception as e:
            st.error(f"오류: {e}")

    # [3] 회계관리
    elif menu == "회계관리":
        st.subheader("💰 재정 수입/지출 관리")
        try:
            client = get_google_sheet()
            sh = client.open("지방회_시스템")
            df = pd.DataFrame(sh.worksheet("finance").get_all_records())

            if not df.empty:
                df['amount'] = pd.to_numeric(df['amount'].astype(str).str.replace(',', ''), errors='coerce').fillna(0)
                t_in = df[df['type'] == '수입']['amount'].sum()
                t_out = df[df['type'] == '지출']['amount'].sum()
                
                c1, c2, c3 = st.columns(3)
                c1.metric("수입", f"€ {int(t_in):,}")
                c2.metric("지출", f"€ {int(t_out):,}")
                c3.metric("잔액", f"€ {int(t_in - t_out):,}")
                st.dataframe(df)
                
                if user['role'] == 'admin':
                    pending = df[df['status'] == '대기']
                    if not pending.empty:
                        st.write("### 👑 결재 대기")
                        for idx, row in pending.iterrows():
                            c1, c2, c3 = st.columns([3, 1, 1])
                            with c1: st.write(f"{row['category']} (€{row['amount']:,})")
                            with c2: 
                                if row['receipt_url']: st.link_button("영수증", row['receipt_url'])
                            with c3:
                                if st.button("승인", key=f"f_{idx}"):
                                    approve_finance(idx)
                                    st.success("승인됨")
                                    time.sleep(1)
                                    st.rerun()

            if user['role'] in ['treasurer', 'admin']:
                st.write("---")
                with st.form("fin_form"):
                    c1, c2 = st.columns(2)
                    f_date = c1.date_input("날짜", datetime.today())
                    f_type = c2.radio("구분", ["수입", "지출"], horizontal=True)
                    f_cat = st.text_input("항목")
                    f_amt = st.number_input("금액", min_value=0)
                    f_desc = st.text_input("내용")
                    f_file = st.file_uploader("영수증")
                    
                    if st.form_submit_button("저장"):
                        with st.spinner("저장 중..."):
                            url = ""
                            if f_file:
                                fid = st.secrets["drive_folder_id"]
                                s_url = st.secrets["upload_script_url"]
                                url = upload_file_via_script(f_file, f"영수증_{f_cat}", fid, s_url)
                            
                            log_finance(f_date, f_type, f_cat, f_amt, f_desc, url, "대기")
                            st.success("저장됨!")
                            time.sleep(1)
                            st.rerun()
        except Exception as e:
            st.error(f"오류: {e}")
