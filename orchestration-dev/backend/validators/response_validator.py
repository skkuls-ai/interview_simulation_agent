from pydantic import BaseModel, Field

class ResponseValidationResult(BaseModel):
    is_valid: bool = Field(description="답변 유효성 통과 여부")
    action_required: str = Field(description="SUCCESS, RETRY_SHORT, RETRY_NO_AUDIO 중 하나")
    message: str = Field(description="사용자 안내 메시지 또는 로그")

def validate_user_response(
    stt_text: str, 
    audio_duration: float, 
    vision_frames_count: int
) -> ResponseValidationResult:
    """사용자의 음성/STT 및 표정 데이터 수집 유효성 검증 (0.001초 완료)"""
    
    clean_text = stt_text.strip()
    
    # 1. 음성 시간 또는 STT 결과 부실 (무음/단답)
    if audio_duration < 1.0 or len(clean_text) == 0:
        return ResponseValidationResult(
            is_valid=False,
            action_required="RETRY_NO_AUDIO",
            message="음성이 제대로 입력되지 않았습니다. 다시 말씀해 주세요."
        )
    
    # 2. 3자 미만의의 의미없는 단답 ("네", "글쎄요")
    if len(clean_text) < 3:
        return ResponseValidationResult(
            is_valid=False,
            action_required="RETRY_SHORT",
            message="답변이 너무 짧습니다. 조금 더 구체적으로 말씀해 주세요."
        )
        
    # 3. 비언어(표정) 데이터 누락 경고 (진행은 시키되 경고)
    if vision_frames_count == 0:
        # 카메라 데이터가 없어도 진행은 시키는 경우
        pass

    return ResponseValidationResult(
        is_valid=True,
        action_required="SUCCESS",
        message="유효한 답변입니다."
    )