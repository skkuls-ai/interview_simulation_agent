from google import genai
from google.genai import types
from pydantic import BaseModel, Field

# 기획서 기준 면접관 구분: tech(기술), behavioral(인성/조직적합성), job(직무)
class QuestionItem(BaseModel):
    id: str = Field(description="질문 ID (예: Q-01, Q-02)")
    interviewer: str = Field(description="면접관 종류 (tech, behavioral, job)")
    question: str = Field(description="면접 질문 내용")
    expected_element: str = Field(default="", description="질문을 통해 확인하고자 하는 기대 평가 요소")

class QuestionValidationResult(BaseModel):
    is_valid: bool = Field(description="검증 통과 여부")
    reason: str = Field(description="검증 결과 또는 보정 사유")
    adjusted_questions: list[QuestionItem] = Field(description="보정된 질문 리스트")

def validate_interview_questions(
    questions: list[dict], 
    resume_summary: str, 
    jd_summary: str,
    client: genai.Client = None,
    run_llm_check: bool = True  # LLM 검사는 Should (선택적 실행)
) -> QuestionValidationResult:
    
    # ----------------------------------------------------
    # STEP 1. 코드 기반 필수 검사 (Code First Validation)
    # ----------------------------------------------------
    seen_ids = set()
    seen_questions = set()
    code_validated_questions = []

    for idx, q in enumerate(questions):
        q_id = str(q.get("id", f"Q-{idx+1}"))
        q_interviewer = q.get("interviewer", "tech")
        q_text = q.get("question", "").strip()
        q_expected = q.get("expected_element", "").strip()

        # 1-1. 질문 내용 유효성
        if not q_text:
            return QuestionValidationResult(
                is_valid=False,
                reason=f"질문 ID [{q_id}]의 질문 내용이 비어있습니다.",
                adjusted_questions=[]
            )

        # 1-2. ID 중복 확인
        if q_id in seen_ids:
            return QuestionValidationResult(
                is_valid=False,
                reason=f"질문 ID [{q_id}]가 중복되었습니다.",
                adjusted_questions=[]
            )
        seen_ids.add(q_id)

        # 1-3. 질문 텍스트 중복 확인
        if q_text in seen_questions:
            return QuestionValidationResult(
                is_valid=False,
                reason=f"중복된 질문 내용이 존재합니다: '{q_text}'",
                adjusted_questions=[]
            )
        seen_questions.add(q_text)

        code_validated_questions.append(
            QuestionItem(
                id=q_id,
                interviewer=q_interviewer,
                question=q_text,
                expected_element=q_expected
            )
        )

    # 코드 검증 실패 요소가 없고 LLM 검사를 진행하지 않는 경우 즉시 반환
    if not run_llm_check or client is None:
        return QuestionValidationResult(
            is_valid=True,
            reason="코드 기반 규칙 검사(ID, 중복, 필수 요소) 통과",
            adjusted_questions=code_validated_questions
        )

    # ----------------------------------------------------
    # STEP 2. LLM 기반 질적 검사 (Should / Optional)
    # ----------------------------------------------------
    prompt = f"""
    당신은 면접 질문 검증관입니다.
    생성된 질문 세트가 지원자 이력 및 JD 요구사항에 적합한지 검증하고 필요시 보정하세요.

    [지원자 이력 요약]: {resume_summary}
    [JD 요구사항]: {jd_summary}
    [검증 대상 질문 세트]: {[q.model_dump() for q in code_validated_questions]}

    [검증 기준]:
    1. 각 질문이 지원자 이력 및 JD 요구사항 범위 내에 있는가?
    2. 30초 내에 핵심을 답변할 수 있는 규모인가?
    3. 면접관 종류(tech: 기술, behavioral: 인성/성향, job: 직무역량)에 부합하는 질문인가?
    """

    try:
        response = client.models.generate_content(
            model='gemini-1.5-flash',
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=QuestionValidationResult,
                temperature=0.1,
            ),
        )
        return response.parsed
    except Exception as e:
        # LLM 검사 실패 시 코드 검증 결과로 Fallback
        return QuestionValidationResult(
            is_valid=True,
            reason=f"LLM 검사 중 오류가 발생하여 코드 검증 결과로 대체합니다: {str(e)}",
            adjusted_questions=code_validated_questions
        )