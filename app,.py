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
st.set_page_config(page_title="유럽직할지방회 행정 시스템", layout="wide")

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

# 파일 업로드 (Apps Script)
def upload_file_via_script(file_obj, filename, folder_id, script_url):
    file_content = file_obj.read()
    file_b64 = base64.b64encode(file_content).decode('utf-8')
    payload = {'folder_id': folder_id, 'filename': filename, 'mimeType': file_obj.type, 'fileBase64': file_b64}
    response = requests.post(script_url, json=payload)
    if response.status_code == 200:
        result = response.json()
        if result.get('status') == 'success': return result.get('fileUrl')
        else: raise Exception(f"스크립트 오류: {result.get('message')}")
    else: raise Exception(f"통신 오류: {response.text}")

# --- 기록 함수들 ---
def log_document(date, title, writer, url, status):
    get_google_sheet().open("지방회_시스템").worksheet("documents").append_row([str(date), title, writer, url, status])

def approve_document(row_idx):
    get_google_sheet().open("지방회_시스템").worksheet("documents").update_cell(row_idx + 2, 5, "승인완료") 

def log_finance(date, f_type, category, amount, desc, url, status):
    get_google_sheet().open("지방회_시스템").worksheet("finance").append_row([str(date), f_type, category, amount, desc, url, status])

def approve_finance(row_idx):
    get_google_sheet().open("지방회_시스템").worksheet("finance").update_cell(row_idx + 2, 7, "승인완료")

# [Update] 일정 등록 (시작일, 종료일 분리)
def log_schedule(start, end, title, location, desc):
    get_google_sheet().open("지방회_시스템").worksheet("schedule").append_row([str(start), str(end), title, location, desc])

def log_task(due_date, task, assignee, status, note):
    get_google_sheet().open("지방회_시스템").worksheet("tasks").append_row([str(due_date), task, assignee, status, note])

def update_task_status(row_idx, new_status):
    get_google_sheet().open("지방회_시스템").worksheet("tasks").update_cell(row_idx + 2, 4, new_status)

# ------------------------------------------------------------------
# 2. 로그인
# ------------------------------------------------------------------
if 'logged_in' not in st.session_state: st.session_state.logged_in = False

if not st.session_state.logged_in:
    st.header("🔒 유럽직할지방회 임원 로그인")
    with st.form("login"):
        uid = st.text_input("아이디")
        upw = st.text_input("비밀번호", type="password")
        if st.form_submit_button("로그인"):
            try:
                users = get_google_sheet().open("지방회_시스템").worksheet("users").get_all_records()
                found = False
                for u in users:
                    if str(u['username']) == str(uid) and str(u['password']) == str(upw):
                        st.session_state.logged_in = True
                        st.session_state.user = u
                        found = True
                        st.rerun()
                if not found: st.error("정보 불일치")
            except Exception as e: st.error(f"오류: {e}")

else:
    # ------------------------------------------------------------------
    # 3. 메인 업무 화면
    # ------------------------------------------------------------------
    user = st.session_state.user
    
    with st.sidebar:
        st.write(f"👤 **{user['name']}** ({user['role']})")
        menu = st.radio("메뉴", ["대시보드", "일정캘린더", "업무진행", "문서관리", "회계관리"])
        if st.button("로그아웃"):
            st.session_state.logged_in = False
            st.rerun()

    st.title("🇪🇺 유럽직할지방회 행정 시스템")

    # [1] 대시보드
    if menu == "대시보드":
        st.subheader("📊 종합 현황")
        try:
            sh = get_google_sheet().open("지방회_시스템")
            df_doc = pd.DataFrame(sh.worksheet("documents").get_all_records())
            df_fin = pd.DataFrame(sh.worksheet("finance").get_all_records())
            df_task = pd.DataFrame(sh.worksheet("tasks").get_all_records())

            # 계산
            p_doc = len(df_doc[df_doc['status'] == '대기']) if not df_doc.empty else 0
            
            balance = 0
            if not df_fin.empty:
                df_fin['amount'] = pd.to_numeric(df_fin['amount'].astype(str).str.replace(',', ''), errors='coerce').fillna(0)
                income = df_fin[df_fin['type'] == '수입']['amount'].sum()
                expense = df_fin[df_fin['type'] == '지출']['amount'].sum()
                balance = income - expense
            
            p_task = len(df_task[df_task['status'] == '진행중']) if not df_task.empty else 0

            c1, c2, c3 = st.columns(3)
            c1.metric("승인 대기 문서", f"{p_doc}건", delta_color="inverse")
            c2.metric("진행 중인 업무", f"{p_task}건", "확인 필요" if p_task > 0 else "완료")
            c3.metric("재정 잔액", f"€ {int(balance):,}")
            
            st.divider()
            
            # [Update] 다가오는 일정 (시작일/종료일 로직 적용)
            st.write("##### 📅 다가오는 일정 (Next 3)")
            schedule_data = sh.worksheet("schedule").get_all_records()
            if schedule_data:
                df_sch = pd.DataFrame(schedule_data)
                df_sch['start_date'] = pd.to_datetime(df_sch['start_date'])
                
                # 오늘 이후에 끝나는 일정(진행중 포함) 필터링
                upcoming = df_sch[df_sch['end_date'] >= datetime.today().strftime('%Y-%m-%d')].sort_values('start_date').head(3)
                
                if not upcoming.empty:
                    for _, row in upcoming.iterrows():
                        # 날짜 표시 형식 (하루짜리 vs 기간)
                        s_str = row['start_date'].strftime('%Y-%m-%d')
                        e_str = row['end_date']
                        date_display = s_str if s_str == e_str else f"{s_str} ~ {e_str}"
                        
                        st.info(f"**{date_display}** | {row['title']} (@{row['location']})")
                else:
                    st.write("예정된 일정이 없습니다.")
            else:
                st.write("등록된 일정이 없습니다.")

        except Exception as e:
            st.error(f"대시보드 로딩 중: {e}")

    # [2] 일정캘린더 (수정됨)
    elif menu == "일정캘린더":
        st.subheader("🗓️ 지방회 연간 일정")
        
        c1, c2 = st.columns([2, 1])
        
        with c1:
            st.write("### 📋 전체 일정 목록")
            try:
                sh = get_google_sheet().open("지방회_시스템")
                s_data = sh.worksheet("schedule").get_all_records()
                if s_data:
                    df_s = pd.DataFrame(s_data)
                    df_s['start_date'] = pd.to_datetime(df_s['start_date'])
                    df_s = df_s.sort_values('start_date')
                    
                    # 보여줄 데이터프레임 정리
                    display_df = df_s.copy()
                    display_df['기간'] = display_df.apply(
                        lambda x: x['start_date'].strftime('%Y-%m-%d') if x['start_date'].strftime('%Y-%m-%d') == x['end_date'] 
                        else f"{x['start_date'].strftime('%Y-%m-%d')} ~ {x['end_date']}", axis=1
                    )
                    
                    st.dataframe(
                        display_df[['기간', 'title', 'location', 'description']], 
                        column_config={"title": "일정명", "location": "장소", "description": "내용"},
                        use_container_width=True,
                        hide_index=True
                    )
                else:
                    st.info("등록된 일정이 없습니다.")
            except:
                st.error("일정을 불러오지 못했습니다. 시트 헤더(start_date, end_date)를 확인해주세요.")

        with c2:
            if user['role'] in ['secretary', 'admin']:
                st.write("### ➕ 일정 등록")
                with st.form("add_schedule"):
                    # [Update] 시작일/종료일 분리
                    col_s, col_e = st.columns(2)
                    s_date = col_s.date_input("시작일")
                    e_date = col_e.date_input("종료일", value=s_date)
                    
                    s_title = st.text_input("일정명 (예: 수련회)")
                    s_loc = st.text_input("장소")
                    s_desc = st.text_area("세부내용")
                    
                    if st.form_submit_button("일정 추가"):
                        if e_date < s_date:
                            st.error("종료일은 시작일보다 빠를 수 없습니다.")
                        else:
                            log_schedule(s_date, e_date, s_title, s_loc, s_desc)
                            st.success("등록되었습니다!")
                            time.sleep(1)
                            st.rerun()

    # [3] 업무진행
    elif menu == "업무진행":
        st.subheader("✅ 업무 진행사항 체크")
        try:
            sh = get_google_sheet().open("지방회_시스템")
            t_data = sh.worksheet("tasks").get_all_records()
            
            if user['role'] in ['secretary', 'admin']:
                with st.expander("➕ 새 업무 지시/등록하기"):
                    with st.form("add_task"):
                        c1, c2 = st.columns(2)
                        t_due = c1.date_input("마감일")
                        t_who = c2.text_input("담당자")
                        t_task = st.text_input("할 일")
                        t_note = st.text_input("비고")
                        if st.form_submit_button("등록"):
                            log_task(t_due, t_task, t_who, "대기", t_note)
                            st.rerun()
            
            st.write("---")
            if t_data:
                df_t = pd.DataFrame(t_data)
                tab1, tab2, tab3 = st.tabs(["🔴 대기중", "🟡 진행중", "🟢 완료됨"])
                
                with tab1:
                    waiting = df_t[df_t['status'] == '대기']
                    if not waiting.empty:
                        for idx, row in waiting.iterrows():
                            with st.container(border=True):
                                ca, cb = st.columns([4,1])
                                ca.markdown(f"**{row['task']}** (담당: {row['assignee']}) | 마감: {row['due_date']}")
                                if cb.button("시작", key=f"s_{idx}"):
                                    update_task_status(idx, "진행중")
                                    st.rerun()
                    else: st.info("없음")
                with tab2:
                    ongoing = df_t[df_t['status'] == '진행중']
                    if not ongoing.empty:
                        for idx, row in ongoing.iterrows():
                            with st.container(border=True):
                                ca, cb = st.columns([4,1])
                                ca.markdown(f"**{row['task']}** (담당: {row['assignee']}) | {row['note']}")
                                if cb.button("완료", key=f"d_{idx}"):
                                    update_task_status(idx, "완료")
                                    st.balloons()
                                    st.rerun()
                    else: st.info("없음")
                with tab3:
                    done = df_t[df_t['status'] == '완료']
                    if not done.empty: st.dataframe(done)
                    else: st.write("없음")
            else: st.info("등록된 업무 없음")
        except Exception as e: st.error(f"오류: {e}")

    # [4] 문서관리
    elif menu == "문서관리":
        st.subheader("📄 문서 제출 및 결재")
        try:
            sh = get_google_sheet().open("지방회_시스템")
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
                                if st.button("승인", key=f"doc_{idx}"):
                                    approve_document(idx)
                                    st.rerun()
            if user['role'] in ['secretary', 'admin']: 
                with st.form("doc"):
                    st.write("새 문서 등록")
                    dt = st.text_input("제목")
                    df = st.file_uploader("파일")
                    if st.form_submit_button("제출") and df:
                        with st.spinner("업로드..."):
                            u = upload_file_via_script(df, dt, st.secrets["drive_folder_id"], st.secrets["upload_script_url"])
                            log_document(datetime.today().date(), dt, user['name'], u, "대기")
                            st.rerun()
        except: st.error("문서 오류")

    # [5] 회계관리
    elif menu == "회계관리":
        st.subheader("💰 재정 수입/지출 관리")
        try:
            sh = get_google_sheet().open("지방회_시스템")
            df = pd.DataFrame(sh.worksheet("finance").get_all_records())
            if not df.empty:
                df['amount'] = pd.to_numeric(df['amount'].astype(str).str.replace(',', ''), errors='coerce').fillna(0)
                bal = df[df['type']=='수입']['amount'].sum() - df[df['type']=='지출']['amount'].sum()
                st.metric("현재 잔액", f"€ {int(bal):,}")
                st.dataframe(df)
                if user['role'] == 'admin':
                    pending = df[df['status'] == '대기']
                    if not pending.empty:
                        st.write("### 👑 결재 대기")
                        for idx, row in pending.iterrows():
                            c1, c2, c3 = st.columns([3,1,1])
                            with c1: st.write(f"{row['category']} (€{row['amount']:,})")
                            with c2: 
                                if row['receipt_url']: st.link_button("영수증", row['receipt_url'])
                            with c3:
                                if st.button("승인", key=f"fin_{idx}"):
                                    approve_finance(idx)
                                    st.rerun()
            if user['role'] in ['treasurer', 'admin']:
                with st.form("fin"):
                    st.write("수입/지출 입력")
                    c1, c2 = st.columns(2)
                    ft = c1.radio("구분", ["수입", "지출"], horizontal=True)
                    fa = c2.number_input("금액", min_value=0)
                    fc = st.text_input("항목")
                    ff = st.file_uploader("영수증")
                    if st.form_submit_button("저장") and fc:
                        u = ""
                        if ff: u = upload_file_via_script(ff, f"영수증_{fc}", st.secrets["drive_folder_id"], st.secrets["upload_script_url"])
                        log_finance(datetime.today().date(), ft, fc, fa, "", u, "대기")
                        st.rerun()
        except: st.error("회계 오류")
