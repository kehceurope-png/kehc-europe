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

# [NEW] 수정된 데이터 저장 함수 (엑셀처럼 통째로 저장)
def save_data(sheet_name, df):
    try:
        client = get_google_sheet()
        sh = client.open("지방회_시스템")
        worksheet = sh.worksheet(sheet_name)
        
        # 1. 모든 데이터 지우기 (초기화)
        worksheet.clear()
        
        # 2. 날짜 등이 깨지지 않게 모두 문자열로 변환
        df = df.astype(str)
        
        # 3. 헤더(제목줄) 포함해서 다시 쓰기
        data_to_save = [df.columns.values.tolist()] + df.values.tolist()
        worksheet.update(range_name='A1', values=data_to_save)
        return True
    except Exception as e:
        st.error(f"저장 중 오류 발생: {e}")
        return False

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

# --- 기존 기록 함수들 ---
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
            
            st.write("##### 📅 다가오는 일정 (Next 3)")
            schedule_data = sh.worksheet("schedule").get_all_records()
            if schedule_data:
                df_sch = pd.DataFrame(schedule_data)
                df_sch['start_date'] = pd.to_datetime(df_sch['start_date'])
                
                upcoming = df_sch[df_sch['end_date'] >= datetime.today().strftime('%Y-%m-%d')].sort_values('start_date').head(3)
                
                if not upcoming.empty:
                    for _, row in upcoming.iterrows():
                        s_str = row['start_date'].strftime('%Y-%m-%d')
                        e_str = row['end_date']
                        date_display = s_str if s_str == e_str else f"{s_str} ~ {e_str}"
                        st.info(f"**{date_display}** | {row['title']} (@{row['location']})")
                else: st.write("예정된 일정이 없습니다.")
            else: st.write("등록된 일정이 없습니다.")

        except Exception as e: st.error(f"대시보드 로딩 중: {e}")

    # [2] 일정캘린더
    elif menu == "일정캘린더":
        st.subheader("🗓️ 지방회 연간 일정")
        
        try:
            sh = get_google_sheet().open("지방회_시스템")
            s_data = sh.worksheet("schedule").get_all_records()
            df_s = pd.DataFrame(s_data) if s_data else pd.DataFrame(columns=['start_date','end_date','title','location','description'])

            # --- [NEW] 수정 모드 ---
            if user['role'] in ['secretary', 'admin']:
                edit_mode = st.toggle("✏️ 수정/삭제 모드 켜기 (내용을 고치고 엔터를 치세요)", value=False)
                
                if edit_mode:
                    st.warning("⚠️ 내용을 직접 수정하거나 행을 삭제할 수 있습니다. 수정 후 반드시 아래 '변경사항 저장' 버튼을 눌러주세요.")
                    # 엑셀처럼 편집 가능한 표 (행 삭제 가능)
                    edited_df = st.data_editor(df_s, num_rows="dynamic", use_container_width=True)
                    
                    if st.button("💾 변경사항 저장하기"):
                        if save_data("schedule", edited_df):
                            st.success("저장되었습니다!")
                            time.sleep(1)
                            st.rerun()
                else:
                    # 보기 모드 (예쁘게 보여주기)
                    if not df_s.empty:
                        df_s['start_date'] = pd.to_datetime(df_s['start_date'])
                        df_s = df_s.sort_values('start_date')
                        display_df = df_s.copy()
                        display_df['기간'] = display_df.apply(lambda x: x['start_date'].strftime('%Y-%m-%d') if x['start_date'].strftime('%Y-%m-%d') == x['end_date'] else f"{x['start_date'].strftime('%Y-%m-%d')} ~ {x['end_date']}", axis=1)
                        st.dataframe(display_df[['기간', 'title', 'location', 'description']], use_container_width=True, hide_index=True)
                    
                    # 일반 등록 폼
                    with st.expander("➕ 새 일정 등록하기", expanded=False):
                        with st.form("add_schedule"):
                            c1, c2 = st.columns(2)
                            s_d = c1.date_input("시작일")
                            e_d = c2.date_input("종료일", value=s_d)
                            s_t = st.text_input("일정명")
                            s_l = st.text_input("장소")
                            s_de = st.text_area("내용")
                            if st.form_submit_button("저장"):
                                log_schedule(s_d, e_d, s_t, s_l, s_de)
                                st.rerun()
            else:
                 # 일반 사용자 보기 전용
                 if not df_s.empty: st.dataframe(df_s)

        except Exception as e: st.error(f"오류: {e}")

    # [3] 업무진행
    elif menu == "업무진행":
        st.subheader("✅ 업무 진행사항")
        try:
            sh = get_google_sheet().open("지방회_시스템")
            t_data = sh.worksheet("tasks").get_all_records()
            df_t = pd.DataFrame(t_data) if t_data else pd.DataFrame(columns=['due_date','task','assignee','status','note'])

            if user['role'] in ['secretary', 'admin']:
                edit_mode = st.toggle("✏️ 수정/삭제 모드 켜기", value=False)
                if edit_mode:
                    st.warning("⚠️ 상태, 담당자, 오타 등을 직접 수정하세요.")
                    edited_t = st.data_editor(df_t, num_rows="dynamic", use_container_width=True)
                    if st.button("💾 변경사항 저장"):
                        if save_data("tasks", edited_t):
                            st.success("저장됨!"); st.rerun()
                else:
                    # 보기 모드 (카드형)
                    st.write("---")
                    with st.expander("➕ 업무 등록"):
                        with st.form("add_task"):
                            c1,c2 = st.columns(2)
                            td = c1.date_input("마감")
                            th = c2.text_input("담당")
                            tt = st.text_input("할일")
                            tn = st.text_input("비고")
                            if st.form_submit_button("등록"):
                                log_task(td, tt, th, "대기", tn); st.rerun()
                    
                    if not df_t.empty:
                        t1, t2, t3 = st.tabs(["대기", "진행중", "완료"])
                        with t1:
                            for i, r in df_t[df_t['status']=='대기'].iterrows():
                                c_a, c_b = st.columns([4,1])
                                c_a.write(f"**{r['task']}** ({r['assignee']}) | ~{r['due_date']}")
                                if c_b.button("시작", key=f"s{i}"): update_task_status(i,"진행중"); st.rerun()
                        with t2:
                            for i, r in df_t[df_t['status']=='진행중'].iterrows():
                                c_a, c_b = st.columns([4,1])
                                c_a.write(f"**{r['task']}** ({r['note']})")
                                if c_b.button("완료", key=f"e{i}"): update_task_status(i,"완료"); st.rerun()
                        with t3:
                             st.dataframe(df_t[df_t['status']=='완료'])

        except Exception as e: st.error(f"오류: {e}")

    # [4] 문서관리
    elif menu == "문서관리":
        st.subheader("📄 문서 관리")
        try:
            sh = get_google_sheet().open("지방회_시스템")
            df = pd.DataFrame(sh.worksheet("documents").get_all_records())
            
            if user['role'] == 'admin':
                edit_mode = st.toggle("✏️ 문서 기록 수정 모드 (파일 자체는 수정불가)", value=False)
                if edit_mode:
                    st.info("💡 제목이나 작성자, 날짜의 오타를 수정할 수 있습니다.")
                    # 파일 URL은 건드리면 안되므로 주의
                    edited_doc = st.data_editor(df, num_rows="dynamic", use_container_width=True)
                    if st.button("💾 변경사항 저장"):
                        save_data("documents", edited_doc); st.success("저장됨!"); st.rerun()
                else:
                    # 결재 모드
                    if not df.empty:
                        pending = df[df['status'] == '대기']
                        if not pending.empty:
                            st.write("### 👑 결재 대기")
                            for idx, row in pending.iterrows():
                                c1, c2, c3 = st.columns([3,1,1])
                                with c1: st.write(f"**{row['title']}**")
                                with c2: st.link_button("보기", row['file_url'])
                                with c3:
                                    if st.button("승인", key=f"d_{idx}"): approve_document(idx); st.rerun()
                        st.write("---")
                        st.dataframe(df[['date', 'title', 'writer', 'status', 'file_url']])
            
            # 일반 보기
            elif not df.empty:
                st.dataframe(df[['date', 'title', 'writer', 'status', 'file_url']])

            if user['role'] in ['secretary', 'admin'] and not st.session_state.get('edit_mode', False): 
                with st.expander("📤 새 문서 등록"):
                    with st.form("doc"):
                        dt = st.text_input("제목")
                        df_f = st.file_uploader("파일")
                        if st.form_submit_button("제출") and df_f:
                            with st.spinner("업로드..."):
                                u = upload_file_via_script(df_f, dt, st.secrets["drive_folder_id"], st.secrets["upload_script_url"])
                                log_document(datetime.today().date(), dt, user['name'], u, "대기")
                                st.rerun()
        except: st.error("오류")

    # [5] 회계관리
    elif menu == "회계관리":
        st.subheader("💰 재정 관리")
        try:
            sh = get_google_sheet().open("지방회_시스템")
            df = pd.DataFrame(sh.worksheet("finance").get_all_records())
            
            if user['role'] in ['treasurer', 'admin']:
                edit_mode = st.toggle("✏️ 장부 수정 모드", value=False)
                if edit_mode:
                    st.warning("⚠️ 금액이나 항목을 직접 수정할 수 있습니다.")
                    edited_fin = st.data_editor(df, num_rows="dynamic", use_container_width=True)
                    if st.button("💾 장부 저장"):
                        save_data("finance", edited_fin); st.success("저장됨!"); st.rerun()
                else:
                    # 일반 모드
                    if not df.empty:
                        df['amount'] = pd.to_numeric(df['amount'].astype(str).str.replace(',', ''), errors='coerce').fillna(0)
                        bal = df[df['type']=='수입']['amount'].sum() - df[df['type']=='지출']['amount'].sum()
                        st.metric("현재 잔액", f"€ {int(bal):,}")
                        
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
                                        if st.button("승인", key=f"f_{idx}"): approve_finance(idx); st.rerun()
                        st.dataframe(df)
                    
                    with st.expander("📝 수입/지출 입력"):
                        with st.form("fin"):
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
            else:
                if not df.empty: st.dataframe(df)

        except: st.error("오류")
