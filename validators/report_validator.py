from google import genai
from google.genai import types
from pydantic import BaseModel, Field

class FinalReportValidationResult(BaseModel):
    is_valid: bool = Field(description="종합 리포트 검증 통과 여부")
    has_contradiction: bool = Field(description="개별 피드백과 종합 피드백 간 논리적 모순 존재 여부")
    reason: str = Field(description="검증 결과 및 모순점 설명")
    final_score: int = Field(description="검수 완료된 최종 종합 점수 (0~100)")
    summary_feedback: str = Field(description="최종 총평 및 보정된 종합 피드백")

def validate_final_report(
    interview_history: list[dict], 
    generated_report: dict,
    client: genai.Client
) -> FinalReportValidationResult:
    """면접 전체 종합 평가 모순 검증"""

    prompt = f"""
    당신은 수석 면접 평가 검수관입니다. 
    전체 면접 이력(개별 질문/답변/피드백)과 최종 생성된 종합 리포트를 비교 검증하세요.

    [전체 면접 이력]: {interview_history}
    [생성된 종합 리포트]: {generated_report}

    [검증 기준]:
    1. 개별 질문 피드백들의 점수/평가와 종합 리포트의 결론에 모순이 없는가?
    2. 모든 질문에 대한 분석 요소가 빠짐없이 포함되었는가?
    3. 모순이 발견되면 최종 점수와 총평을 올바르게 수정하세요.
    """

    response = client.models.generate_content(
        model='gemini-3.7-flash',
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=FinalReportValidationResult,
            temperature=0.1,
        ),
    )

    return response.parsed