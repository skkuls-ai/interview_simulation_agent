from google import genai
from google.genai import types
from pydantic import BaseModel, Field

class FeedbackValidationResult(BaseModel):
    is_valid: bool = Field(description="피드백 및 점수의 타당성 여부")
    corrected_score: int = Field(description="내용 및 비언어 지표(시선/표정)를 반영하여 보정된 점수 (0~100)")
    corrected_feedback: str = Field(description="보정된 피드백 텍스트")
    reason: str = Field(description="검증/보정 사유")

def validate_single_feedback(
    question: str, 
    user_answer: str, 
    raw_score: int,
    raw_feedback: str,
    visual_metrics: dict = None,  # 시선 처리, 표정 분석 데이터 (선택)
    client: genai.Client = None
) -> FeedbackValidationResult:
    """
    개별 질문 피드백 검증
    - 반영 대상: 답변의 내용적 타당성 + 시선/표정 등 카메라 비언어 지표
    - 반영 금지: 지원자의 긴장도, 당황함 등 심리 상태 추론 및 긴장도 기반 점수 감점
    """

    visual_info_str = f"시선 처리: {visual_metrics.get('gaze', 'N/A')}, 표정: {visual_metrics.get('expression', 'N/A')}" if visual_metrics else "비언어 지표 없음"

    prompt = f"""
    당신은 면접 피드백 검수관입니다. 
    면접관 에이전트가 부여한 평가 점수와 피드백 내용이 지침 기준에 맞는지 검증하고 보정하세요.

    [질문]: {question}
    [사용자 답변]: {user_answer}
    [카메라 지표(시선/표정)]: {visual_info_str}
    [생성된 점수]: {raw_score}
    [생성된 피드백]: {raw_feedback}

    [검증 및 점수 반영 지침]:
    1. **내용적 타당성:** 답변 내용이 질문 의도에 부합하는지 평가합니다.
    2. **비언어 지표 반영 허용:** 시선 처리(아이컨택 유지 여부) 및 표정(밝은 표정, 덤덤함 등)은 평가 요소로 반영할 수 있습니다.
    3. **★ 긴장도 평가 및 추론 금지 ★:** 
       - "지원자가 많이 긴장한 것으로 보임", "당황하여 목소리가 떨림" 등 지원자의 '긴장도' 및 '심리 상태'를 직접 언급하거나 이를 이유로 감점하는 것은 절대 금지합니다.
       - 긴장도 관련 표현이 피드백에 포함되어 있다면 '시선 불안정' 또는 '표정 정체' 등 객관적으로 관찰 가능한 비언어적 행동 표현으로 교체하거나 제거하세요.
    """

    response = client.models.generate_content(
        model='gemini-1.5-flash',
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=FeedbackValidationResult,
            temperature=0.1,
        ),
    )

    return response.parsed