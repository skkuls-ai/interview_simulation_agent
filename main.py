import os
from dotenv import load_dotenv
from google import genai

from validators.question_validator import validate_interview_questions
from validators.response_validator import validate_user_response
from validators.feedback_validator import validate_single_feedback
from validators.report_validator import validate_final_report

# 1. .env 파일 로드
load_dotenv()

# 2. API 키 확인
api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    raise ValueError(".env 파일에서 GEMINI_API_KEY를 찾을 수 없습니다. .env 파일 위치와 키 이름을 확인해 주세요.")

# 3. Gemini Client 초기화
client = genai.Client(api_key=api_key)

# --- 1. 질문 검증 테스트 ---
questions_sample = [
    {"id": 1, "interviewer": "strict", "question": "이전 프로젝트에서 백엔드 동시성 문제를 해결한 경험을 30초 내로 설명하세요."},
    {"id": 2, "interviewer": "friendly", "question": "우리 회사에 지원하시면서 가장 기대했던 점은 무엇인가요?"}
]
v1_result = validate_interview_questions(
    questions=questions_sample,
    resume_summary="Python FastApi 개발 2년 경력",
    jd_summary="백엔드 대용량 트래픽 처리 담당자 구인",
    client=client
)
print("[V1 질문 검증 결과]:", v1_result.is_valid)

# --- 2. 사용자 답변 유효성 검증 테스트 (코드 기반 - 0초) ---
v2_result = validate_user_response(
    stt_text="어...", 
    audio_duration=0.8, 
    vision_frames_count=10
)
print("[V2 답변 검증 결과]:", v2_result.action_required, "-", v2_result.message)

# --- 3. 개별 피드백 검증 테스트 ---
v3_result = validate_single_feedback(
    question="백엔드 동시성 해결 경험이 있나요?",
    user_answer="네 저는 맛집 탐방을 좋아해서 주말마다 맛집에 갑니다.",
    raw_score=85,
    raw_feedback="자신의 취미를 솔직하게 대답해 주었습니다.",
    non_verbal_summary="긴장도 높음, 아이콘택트 부족",
    client=client
)
print("[V3 피드백 검증 결과 - 보정 점수]:", v3_result.corrected_score)
print("[V3 피드백 검증 결과 - 보정 피드백]:", v3_result.corrected_feedback)