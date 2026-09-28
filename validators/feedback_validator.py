from google import genai
from google.genai import types
from pydantic import BaseModel, Field

class FeedbackValidationResult(BaseModel):
    is_valid: bool = Field(description="피드백 적절성 여부")
    corrected_score: int = Field(description="검증/보정된 점수 (0~100)")
    corrected_feedback: str = Field(description="보정된 최종 피드백 텍스트")
    reason: str = Field(description="검증 의견")

def validate_single_feedback(
    question: str, 
    user_answer: str, 
    raw_score: int,
    raw_feedback: str,
    non_verbal_summary: str,
    client: genai.Client
) -> FeedbackValidationResult:
    """개별 질문 피드백 검증 (백그라운드 비동기 처리 권장)"""

    prompt = f"""
    당신은 면접 피드백 검수관입니다. 면접관 에이전트가 생성한 평가와 피드백이 타당한지 검증하세요.

    [질문]: {question}
    [사용자 답변]: {user_answer}
    [비언어 상태]: {non_verbal_summary}
    [기존 점수]: {raw_score}
    [기존 피드백]: {raw_feedback}

    [검증 기준]:
    1. 답변이 질문과 완전히 동문서답인데 고득점을 주지 않았는가?
    2. 피드백이 무조건적인 비난이 아닌 구체적 개선 방향을 제시하는가?
    3. 점수와 피드백 내용 간 수위가 상호 일치하는가?
    4. 문제가 있다면 점수와 피드백을 보정하여 출력하세요.
    """

    response = client.models.generate_content(
        model='gemini-3.7-flash',
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=FeedbackValidationResult,
            temperature=0.1,
        ),
    )

    return response.parsed