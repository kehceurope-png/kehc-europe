import json # 맨 위에 이 줄이 없으면 추가해주세요!
import streamlit as st
import gspread
from google.oauth2.service_account import Credentials

# 페이지 설정
st.set_page_config(page_title="유럽직할지방회 임원 시스템", layout="wide")

# 1. 구글 시트 연결하기 (비밀 열쇠 사용)
# 캐싱( @st.cache_resource )을 사용해서 매번 로그인하지 않도록 함
@st.cache_resource
def get_connection():
    # Streamlit Secrets에서 열쇠 꺼내기 (문자열을 JSON으로 변환)
    key_dict = json.loads(st.secrets["service_account_json"])
    
    # 구글에 접속할 권한 설정
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_info(key_dict, scopes=scopes)
    client = gspread.authorize(creds)
    
    return client

# 2. 화면 구성
st.title("🇪🇺 유럽직할지방회 임원 행정 시스템")

try:
    # 연결 시도
    client = get_connection()
    
    # 시트 열기 (파일 이름이 정확해야 합니다!)
    # 목사님이 만드신 구글 시트 제목: "2026_지방회_시스템"
    sh = client.open("2026_지방회_시스템")
    
    st.success("✅ 구글 스프레드시트 연결 성공!")
    
    # 'users' 탭의 내용 가져와서 보여주기 (테스트)
    worksheet = sh.worksheet("users")
    data = worksheet.get_all_records()
    
    st.subheader("📋 현재 등록된 사용자 (DB 테스트)")
    if data:
        st.dataframe(data)
    else:
        st.info("아직 등록된 사용자가 없습니다. 구글 시트 'users' 탭에 데이터를 입력해보세요.")

except Exception as e:
    st.error(f"⚠️ 연결 실패! 다음을 확인해주세요:\n1. 구글 시트 제목이 '2026_지방회_시스템'이 맞나요?\n2. 시트에 로봇 이메일(client_email)을 '편집자'로 초대했나요?\n\n에러 메시지: {e}")
