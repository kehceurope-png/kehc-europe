import streamlit as st
import gspread
import json
from google.oauth2.service_account import Credentials
import time

# ------------------------------------------------------------------
# 1. 설정 및 연결 (기존과 동일)
# ------------------------------------------------------------------
st.set_page_config(page_title="유럽직할지방회 임원 시스템", layout="wide")

# 기존의 get_connection 함수 전체를 지우고 아래 걸로 교체하세요

@st.cache_resource
def get_connection():
    # 이제 json.loads가 필요 없습니다! 바로 가져옵니다.
    key_dict = st.secrets["gcp_service_account"]
    
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_info(key_dict, scopes=scopes)
    client = gspread.authorize(creds)
    return client

# ------------------------------------------------------------------
# 2. 로그인 관련 함수
# ------------------------------------------------------------------
def check_login(username, password):
    """구글 시트에서 아이디/비번 확인"""
    try:
        client = get_connection()
        sh = client.open("지방회_시스템")
        worksheet = sh.worksheet("users")
        records = worksheet.get_all_records()
        
        for user in records:
            # 문자열로 변환해서 비교 (숫자로 입력될 경우 대비)
            if str(user['username']) == str(username) and str(user['password']) == str(password):
                return user # 로그인 성공 시 사용자 정보 반환
        return None # 실패
    except Exception as e:
        st.error(f"로그인 확인 중 오류 발생: {e}")
        return None

# 세션 상태 초기화 (로그인 상태 기억하기 위함)
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
if 'user_info' not in st.session_state:
    st.session_state.user_info = None

# ------------------------------------------------------------------
# 3. 화면 구성 (메인 로직)
# ------------------------------------------------------------------

# (A) 로그인이 안 된 상태 -> 로그인 화면 표시
if not st.session_state.logged_in:
    st.header("🔒 유럽직할지방회 임원 로그인")
    
    with st.form("login_form"):
        input_id = st.text_input("아이디")
        input_pw = st.text_input("비밀번호", type="password")
        submit = st.form_submit_button("로그인")
        
        if submit:
            user = check_login(input_id, input_pw)
            if user:
                st.session_state.logged_in = True
                st.session_state.user_info = user
                st.success(f"{user['name']} 목사님, 환영합니다!")
                time.sleep(1)
                st.rerun() # 화면 새로고침
            else:
                st.error("아이디 또는 비밀번호가 잘못되었습니다.")

# (B) 로그인 된 상태 -> 업무 화면 표시
else:
    user = st.session_state.user_info
    
    # 사이드바 (로그아웃 버튼 및 정보)
    with st.sidebar:
        st.write(f"접속자: {user['name']} ({user['role']})")
        if st.button("로그아웃"):
            st.session_state.logged_in = False
            st.session_state.user_info = None
            st.rerun()
            
    # 메인 화면
    st.title("🇪🇺 유럽직할지방회 행정 시스템")
    
    # 직책에 따른 메뉴 안내 (테스트용)
    if user['role'] == 'admin':
        st.info("관리자(회장) 권한으로 접속하셨습니다. 모든 문서 결재가 가능합니다.")
    elif user['role'] == 'secretary':
        st.info("서기 권한입니다. 회의록 및 문서를 업로드할 수 있습니다.")
    elif user['role'] == 'treasurer':
        st.info("회계 권한입니다. 수입/지출 내역을 관리할 수 있습니다.")
        
    st.write("---")
    st.write("👈 왼쪽 사이드바에서 메뉴를 선택하게 될 예정입니다.")


