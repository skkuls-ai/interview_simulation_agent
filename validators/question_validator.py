from google import genai
from google.genai import types
from pydantic import BaseModel, Field

# 1. 질문 단일 항목에 대한 명확한 스키마 정의 (dict 대신 사용)
class QuestionItem(BaseModel):
    id: int = Field(description="질문 ID")
    interviewer: str = Field(description="면접관 역할 (strict, friendly 등)")
    question: str = Field(description="면접 질문 내용")

# 2. 메인 검증 결과 스키마
class QuestionValidationResult(BaseModel):
    is_valid: bool = Field(description="모든 질문 검증 통과 여부")
    reason: str = Field(description="통과 또는 통과 실패 시 구체적인 이유")
    # list[dict] 대신 list[QuestionItem]으로 변경
    adjusted_questions: list[QuestionItem] = Field(description="수정 및 개선된 질문 리스트 (is_valid가 False일 때 보정한 질문들)")

def validate_interview_questions(
    questions: list[dict], 
    resume_summary: str, 
    jd_summary: str,
    client: genai.Client
) -> QuestionValidationResult:
    """질문 세트 및 면접관 페르소나 검증"""
    
    prompt = f"""
    당신은 모의 면접 질문 검증관입니다.
    생성된 면접 질문들이 다음 기준을 만족하는지 검증하고 필요한 경우 보정하세요.

    [지원자 이력 요약]: {resume_summary}
    [JD 요구사항]: {jd_summary}
    [생성된 질문 세트]: {questions}

    [검증 기준]:
    1. 각 질문이 지원자의 이력 및 JD 요구사항 범위 내에 있는가?
    2. 각 질문이 30초 내에 대답하기에 적절한 규모인가? (너무 거대하거나 3문장 이상의 긴 질문 금지)
    3. 지정된 면접관 페르소나(엄격함, 긴장 풀어줌, 기타)의 어조 및 특성에 부합하는가?
    """

    response = client.models.generate_content(
        model='gemini-3.7-flash',
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=QuestionValidationResult,
            temperature=0.1,
        ),
    )
    
    return response.parsed


# 꼬리질문 전용 검증 결과 스키마
class FollowupValidationResult(BaseModel):
    is_valid: bool = Field(description="꼬리질문 검증 통과 여부")
    reason: str = Field(description="검증 의견 또는 보정 이유")
    adjusted_question: str = Field(description="보정된 최종 꼬리질문 (is_valid가 False일 때 수정된 질문)")

def validate_followup_question(
    previous_question: str,
    user_answer: str,
    generated_followup: str,
    interviewer_persona: str,
    client: genai.Client
) -> FollowupValidationResult:
    """사용자 답변 기반 꼬리질문 검증"""

    prompt = f"""
    당신은 면접 꼬리질문 검수관입니다. 
    면접관이 지원자의 답변을 듣고 던진 꼬리질문이 적절한지 검증하고 필요시 수정하세요.

    [이전 질문]: {previous_question}
    [지원자 답변]: {user_answer}
    [생성된 꼬리질문]: {generated_followup}
    [면접관 페르소나]: {interviewer_persona}

    [검증 기준]:
    1. 꼬리질문이 지원자가 언급한 실제 답변 내용/키워드에 기반하고 있는가? (답변에 없는 헛소리 금지)
    2. 지원자의 답변에서 모호하거나 부족했던 점을 정확히 짚어내는가?
    3. 30초 안에 답변 가능한 범위인가?
    4. 면접관 페르소나({interviewer_persona})의 톤앤매너를 유지하는가?
    """

    response = client.models.generate_content(
        model='gemini-1.5-flash',
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=FollowupValidationResult,
            temperature=0.1,
        ),
    )

    return response.parsed