import streamlit as st
import gspread
import json
import pandas as pd
import requests
import base64
from google.oauth2.service_account import Credentials
from datetime import datetime, timedelta
import time

# ------------------------------------------------------------------
# 1. 설정 및 연결
# ------------------------------------------------------------------
st.set_page_config(page_title="유럽직할지방회", layout="wide", initial_sidebar_state="collapsed")

# 모바일 친화적 스타일 (여백 최소화 & 폰트 조정)
st.markdown("""
    <style>
        .block-container {padding-top: 1rem; padding-bottom: 2rem;}
        [data-testid="stMetricValue"] {font-size: 1.5rem;}
        .stButton button {width: 100%;}
    </style>
""", unsafe_allow_html=True)

@st.cache_resource
def get_google_sheet():
    if "gcp_service_account" in st.secrets:
        key_dict = dict(st.secrets["gcp_service_account"])
        if "\\n" in key_dict["private_key"]:
            key_dict["private_key"] = key_dict["private_key"].replace("\\n", "\n")
    else:
        key_dict = json.loads(st.secrets["service_account_json"], strict=False)

    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_info(key_dict, scopes=scopes)
    client = gspread.authorize(creds)
    return client

# 데이터 저장 함수
def save_data(sheet_name, df):
    try:
        client = get_google_sheet()
        sh = client.open("지방회_시스템")
        worksheet = sh.worksheet(sheet_name)
        worksheet.clear()
        df = df.astype(str)
        data_to_save = [df.columns.values.tolist()] + df.values.tolist()
        worksheet.update(range_name='A1', values=data_to_save)
        return True
    except Exception as e:
        st.error(f"저장 오류: {e}")
        return False

# 파일 업로드 함수
def upload_file_via_script(file_obj, filename, folder_id, script_url):
    try:
        file_content = file_obj.read()
        file_b64 = base64.b64encode(file_content).decode('utf-8')
        payload = {'folder_id': folder_id, 'filename': filename, 'mimeType': file_obj.type, 'fileBase64': file_b64}
        response = requests.post(script_url, json=payload)
        if response.status_code == 200:
            result = response.json()
            if result.get('status') == 'success': return result.get('fileUrl')
            else: raise Exception(f"{result.get('message')}")
        else: raise Exception(f"통신 오류: {response.text}")
    except Exception as e: raise Exception(f"업로드 실패: {e}")

# 기록 함수들
def log_document(date, title, writer, url, status):
    get_google_sheet().open("지방회_시스템").worksheet("documents").append_row([str(date), title, writer, url, status])

def approve_document(row_idx):
    get_google_sheet().open("지방회_시스템").worksheet("documents").update_cell(row_idx + 2, 5, "승인완료") 

def log_finance(date, f_type, category, amount, desc, url, status):
    get_google_sheet().open("지방회_시스템").worksheet("finance").append_row([str(date), f_type, category, amount, desc, url, status])

def approve_finance(row_idx):
    get_google_sheet().open("지방회_시스템").worksheet("finance").update_cell(row_idx + 2, 7, "승인완료")

def log_schedule(start, end, title, location, desc):
    get_google_sheet().open("지방회_시스템").worksheet("schedule").append_row([str(start), str(end), title, location, desc])

def log_task(due_date, task, assignee, status, note):
    get_google_sheet().open("지방회_시스템").worksheet("tasks").append_row([str(due_date), task, assignee, status, note])

def update_task_status(row_idx, new_status):
    get_google_sheet().open("지방회_시스템").worksheet("tasks").update_cell(row_idx + 2, 4, new_status)

# ------------------------------------------------------------------
# 로그인 및 메인
# ------------------------------------------------------------------
if 'logged_in' not in st.session_state: st.session_state.logged_in = False

if not st.session_state.logged_in:
    st.markdown("### 🇪🇺 유럽직할지방회 로그인")
    with st.form("login"):
        uid = st.text_input("아이디")
        upw = st.text_input("비밀번호", type="password")
        if st.form_submit_button("접속하기", type="primary"):
            try:
                users = get_google_sheet().open("지방회_시스템").worksheet("users").get_all_records()
                found = False
                for u in users:
                    if str(u['username']) == str(uid) and str(u['password']) == str(upw):
                        st.session_state.logged_in = True
                        st.session_state.user = u
                        found = True
                        st.rerun()
                if not found: st.error("정보가 일치하지 않습니다.")
            except Exception as e: st.error(f"접속 오류: {e}")
else:
    user = st.session_state.user
    with st.sidebar:
        st.write(f"안녕하세요, **{user['name']}** 목사님")
        menu = st.radio("메뉴 이동", ["대시보드", "일정", "업무", "문서", "재정"])
        if st.button("로그아웃"):
            st.session_state.logged_in = False
            st.rerun()
        
        st.divider()
        with st.expander("📲 앱 설치 방법"):
            st.markdown("""
            **아이폰**: [공유] → [홈 화면에 추가]
            **갤럭시**: [점 3개] → [홈 화면에 추가]
            """)

    # [1] 대시보드
    if menu == "대시보드":
        st.subheader("Dashboard")
        try:
            sh = get_google_sheet().open("지방회_시스템")
            df_doc = pd.DataFrame(sh.worksheet("documents").get_all_records())
            df_fin = pd.DataFrame(sh.worksheet("finance").get_all_records())
            
            # --- 1. 통계 (결재/잔액) ---
            p_doc = len(df_doc[df_doc['status'] == '대기']) if not df_doc.empty else 0
            balance = 0
            p_fin = 0
            if not df_fin.empty:
                df_fin['amount'] = pd.to_numeric(df_fin['amount'].astype(str).str.replace(',', ''), errors='coerce').fillna(0)
                income = df_fin[df_fin['type'] == '수입']['amount'].sum()
                expense = df_fin[df_fin['type'] == '지출']['amount'].sum()
                balance = income - expense
                p_fin = len(df_fin[df_fin['status'] == '대기'])

            c1, c2, c3 = st.columns(3)
            c1.metric("결재 대기", f"{p_doc + p_fin}건", delta="처리 필요" if (p_doc+p_fin)>0 else "완료", delta_color="inverse")
            c2.metric("재정 잔액", f"€ {int(balance):,}")
            c3.write(f"접속자: {user['name']}")
            
            st.divider()

            # --- 2. 회장님 결재 섹션 (One-Touch) ---
            if user['role'] == 'admin':
                if (p_doc + p_fin) > 0:
                    st.write("### ⚡ 빠른 결재 필요")
                    
                    if p_fin > 0:
                        pending_fin = df_fin[df_fin['status'] == '대기']
                        for idx, row in pending_fin.iterrows():
                            with st.container(border=True):
                                col_a, col_b = st.columns([3, 1])
                                col_a.markdown(f"💰 **{row['category']}** (€ {row['amount']:,}) | {row['description']}")
                                if row['receipt_url']: col_a.link_button("영수증", row['receipt_url'])
                                if col_b.button("승인", key=f"d_f_{idx}", type="primary"):
                                    approve_finance(idx); st.toast("승인 완료!"); time.sleep(0.5); st.rerun()

                    if p_doc > 0:
                        pending_doc = df_doc[df_doc['status'] == '대기']
                        for idx, row in pending_doc.iterrows():
                            with st.container(border=True):
                                col_a, col_b = st.columns([3, 1])
                                col_a.markdown(f"📄 **{row['title']}** (작성: {row['writer']})")
                                if row['file_url']: col_a.link_button("문서", row['file_url'])
                                if col_b.button("승인", key=f"d_d_{idx}", type="primary"):
                                    approve_document(idx); st.toast("승인 완료!"); time.sleep(0.5); st.rerun()
                    st.divider()

            # --- 3. 다가오는 일정 (복구됨) ---
            st.write("### 📅 다가오는 일정 (Upcoming)")
            s_data = sh.worksheet("schedule").get_all_records()
            if s_data:
                df_s = pd.DataFrame(s_data)
                if 'start_date' in df_s.columns and 'end_date' in df_s.columns:
                    df_s['start_date'] = pd.to_datetime(df_s['start_date'])
                    # 오늘 이후 종료되는 일정만 필터링 (이미 끝난 건 안 보임)
                    upcoming = df_s[df_s['end_date'] >= datetime.today().strftime('%Y-%m-%d')].sort_values('start_date').head(3)
                    
                    if not upcoming.empty:
                        for _, row in upcoming.iterrows():
                            s_str = row['start_date'].strftime('%Y-%m-%d')
                            e_str = row['end_date']
                            date_msg = s_str if s_str == e_str else f"{s_str} ~ {e_str}"
                            
                            # 카드 형태로 예쁘게 표시
                            st.info(f"**{row['title']}**\n\n🗓️ {date_msg} | 📍 {row['location']}")
                    else:
                        st.caption("예정된 일정이 없습니다.")
                else: st.error("일정 데이터 형식이 맞지 않습니다.")
            else:
                st.caption("등록된 일정이 없습니다.")

        except Exception as e: st.error(f"로딩 오류: {e}")

    # [2] 일정 (등록 및 수정)
    elif menu == "일정":
        st.subheader("Calendar")
        try:
            sh = get_google_sheet().open("지방회_시스템")
            s_data = sh.worksheet("schedule").get_all_records()
            df_s = pd.DataFrame(s_data) if s_data else pd.DataFrame(columns=['start_date','end_date','title','location','description'])

            if user['role'] in ['secretary', 'admin']:
                with st.expander("➕ 일정 등록/수정"):
                    if not df_s.empty:
                         edit_mode = st.toggle("수정 모드", value=False)
                         if edit_mode:
                             edited = st.data_editor(df_s, num_rows="dynamic", use_container_width=True)
                             if st.button("저장"): save_data("schedule", edited); st.rerun()
                    
                    st.write("새 일정 등록")
                    with st.form("sch"):
                        c1, c2 = st.columns(2)
                        sd = c1.date_input("시작")
                        ed = c2.date_input("종료", value=sd)
                        t = st.text_input("제목")
                        l = st.text_input("장소")
                        d = st.text_area("내용")
                        if st.form_submit_button("등록"):
                            log_schedule(sd, ed, t, l, d); st.rerun()

            if not df_s.empty and 'start_date' in df_s.columns:
                df_s['start_date'] = pd.to_datetime(df_s['start_date'])
                df_s = df_s.sort_values('start_date')
                for _, r in df_s.iterrows():
                    with st.container(border=True):
                        st.write(f"**{r['title']}**")
                        st.caption(f"{r['start_date'].strftime('%Y-%m-%d')} ~ {r['end_date']} | @{r['location']}")
                        st.write(r['description'])
        except: st.error("일정 오류")

    # [3] 업무
    elif menu == "업무":
        st.subheader("Tasks")
        try:
            sh = get_google_sheet().open("지방회_시스템")
            t_data = sh.worksheet("tasks").get_all_records()
            df_t = pd.DataFrame(t_data) if t_data else pd.DataFrame()
            
            if user['role'] in ['secretary', 'admin']:
                with st.expander("➕ 업무 등록"):
                    with st.form("tsk"):
                        c1,c2 = st.columns(2)
                        td = c1.date_input("마감")
                        th = c2.text_input("담당")
                        tt = st.text_input("할일")
                        tn = st.text_input("비고")
                        if st.form_submit_button("등록"):
                            log_task(td, tt, th, "대기", tn); st.rerun()

            if not df_t.empty:
                tabs = st.tabs(["대기", "진행", "완료"])
                with tabs[0]:
                    for i, r in df_t[df_t['status']=='대기'].iterrows():
                        c1, c2 = st.columns([4,1])
                        c1.write(f"**{r['task']}** ({r['assignee']})")
                        if c2.button("Start", key=f"s{i}"): update_task_status(i,"진행중"); st.rerun()
                with tabs[1]:
                    for i, r in df_t[df_t['status']=='진행중'].iterrows():
                        c1, c2 = st.columns([4,1])
                        c1.write(f"**{r['task']}**")
                        if c2.button("Done", key=f"d{i}"): update_task_status(i,"완료"); st.rerun()
                with tabs[2]:
                    st.dataframe(df_t[df_t['status']=='완료'], use_container_width=True)
        except: st.error("업무 오류")

    # [4] 문서
    elif menu == "문서":
        st.subheader("Documents")
        try:
            sh = get_google_sheet().open("지방회_시스템")
            df = pd.DataFrame(sh.worksheet("documents").get_all_records())
            
            if user['role'] in ['secretary', 'admin']:
                with st.expander("📤 문서 등록"):
                    with st.form("doc"):
                        dt = st.text_input("제목")
                        df_f = st.file_uploader("파일")
                        if st.form_submit_button("제출") and df_f:
                            with st.spinner("업로드..."):
                                u = upload_file_via_script(df_f, dt, st.secrets["drive_folder_id"], st.secrets["upload_script_url"])
                                log_document(datetime.today().date(), dt, user['name'], u, "대기")
                                st.rerun()
            
            if not df.empty:
                st.dataframe(df[['date', 'title', 'status', 'file_url']], use_container_width=True)
        except: st.error("문서 오류")

    # [5] 재정
    elif menu == "재정":
        st.subheader("Finance")
        try:
            sh = get_google_sheet().open("지방회_시스템")
            df = pd.DataFrame(sh.worksheet("finance").get_all_records())

            if user['role'] in ['treasurer', 'admin']:
                with st.expander("📝 장부 입력/수정"):
                    if not df.empty:
                        edit_mode = st.toggle("수정 모드", value=False)
                        if edit_mode:
                            edited = st.data_editor(df, num_rows="dynamic", use_container_width=True)
                            if st.button("저장"): save_data("finance", edited); st.rerun()
                    
                    st.write("새 내역 입력")
                    with st.form("fin"):
                        c1, c2 = st.columns(2)
                        ft = c1.radio("구분", ["수입", "지출"], horizontal=True)
                        fa = c2.number_input("금액", min_value=0)
                        fc = st.text_input("항목")
                        fd = st.text_input("내용")
                        ff = st.file_uploader("영수증")
                        if st.form_submit_button("저장") and fc:
                            u = ""
                            if ff: u = upload_file_via_script(ff, f"영수증_{fc}", st.secrets["drive_folder_id"], st.secrets["upload_script_url"])
                            log_finance(datetime.today().date(), ft, fc, fa, fd, u, "대기")
                            st.rerun()
            
            if not df.empty:
                st.dataframe(df, use_container_width=True)
        except: st.error("재정 오류")
