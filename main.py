import os
from dotenv import load_dotenv
from google import genai

from validators.question_validator import validate_interview_questions
from validators.response_validator import validate_user_response
from validators.feedback_validator import validate_single_feedback
from validators.report_validator import validate_final_report

load_dotenv()

api_key = os.getenv("GEMINI_API_KEY")
client = genai.Client(api_key=api_key) if api_key else None

print("=== 수정된 검증 모듈 테스트 ===\n")

# 1. 질문 검증 테스트 (기획서 규격 반영)
questions_sample = [
    {
        "id": "Q-TECH-01", 
        "interviewer": "tech", 
        "question": "백엔드 동시성 문제 해결 경험을 30초 내로 설명하세요.",
        "expected_element": "동시성 제어 및 락(Lock) 활용 역량"
    },
    {
        "id": "Q-BEHAVIOR-01", 
        "interviewer": "behavioral", 
        "question": "동료와 의견 충돌이 발생했을 때 어떻게 해결하시나요?",
        "expected_element": "커뮤니케이션 및 협업 능력"
    }
]

v1_result = validate_interview_questions(
    questions=questions_sample,
    resume_summary="Python FastAPI 백엔드 개발자",
    jd_summary="대용량 트래픽 처리 담당자",
    client=client,
    run_llm_check=True
)
print("[V1 질문 검증 통과 여부]:", v1_result.is_valid)
print("[V1 보정 이유]:", v1_result.reason)
print("[V1 보정된 질문 ID 및 면접관]:", [(q.id, q.interviewer) for q in v1_result.adjusted_questions])
print("-" * 50)

# 2. 개별 피드백 검증 테스트 (카메라/비언어 지표 평가 배제 확인)
v3_result = validate_single_feedback(
    question="동시성 제어 해결 경험이 있나요?",
    user_answer="네, Redis 분산락을 도입해 동시 요청 이슈를 해결했습니다.",
    raw_score=90,
    raw_feedback="답변 내용이 우수하며 핵심을 잘 전달했습니다.",
    client=client
)
print("[V3 피드백 검증 보정 점수]:", v3_result.corrected_score)
print("[V3 피드백 내용]:", v3_result.corrected_feedback)