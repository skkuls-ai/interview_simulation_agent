"""개인정보 수집, 이용 동의."""

from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field, model_validator

CONSENT_VERSION = "2026-09-28.2"

CONSENT_TERMS = {
    "version": CONSENT_VERSION,
    "items": [
        {
            "key": "microphone",
            "required": True,
            "title": "음성 녹음과 받아쓰기",
            "detail": "답변 음성은 받아쓰기를 위해 Google Cloud(Vertex AI)로 실시간 전송되어 텍스트로 변환되고, "
                      "변환된 텍스트는 꼬리질문과 평가를 위해 Gemini 모델로 전송됩니다. 음성 파일은 저장하지 않습니다.",
        },
        {
            "key": "camera",
            "required": False,
            "title": "카메라 (시선, 표정 지표)",
            "detail": "브라우저 안에서 시선과 표정을 수치로만 계산해 전송합니다. 영상은 서버로 보내거나 저장하지 않습니다. "
                      "이 지표는 코칭 피드백에만 쓰고 합격, 불합격 판정에는 쓰지 않습니다.",
        },
        {
            "key": "documents",
            "required": False,
            "title": "JD, 이력서, 자기소개서 분석",
            "detail": "질문을 개인화하기 위해 문서 내용을 Google Cloud(Vertex AI)의 Gemini 모델로 보내 분석합니다. "
                      "업로드한 문서와 추출한 원문은 면접 세션이 끝나면 삭제하며, "
                      "끝나지 않은 세션도 24시간이 지나면 자동으로 삭제합니다. 동의하지 않으면 문서 없이 진행합니다.",
        },
        {
            "key": "store_results",
            "required": False,
            "title": "면접 결과 저장",
            "detail": "답변 기록, 평가, 피드백을 저장해 '이전 결과 보기'에서 다시 볼 수 있게 합니다. 언제든 삭제할 수 있습니다. "
                      "동의하지 않으면 결과는 면접 직후 한 번만 보여주고 저장하지 않습니다.",
        },
    ],
}


class ConsentRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str = CONSENT_VERSION
    microphone: bool
    camera: bool = False
    documents: bool = False
    store_results: bool = False
    agreed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @model_validator(mode="after")
    def _required(self) -> "ConsentRecord":
        if not self.microphone:
            raise ValueError("음성 녹음 동의는 필수입니다. 음성으로 답변을 받아야 면접을 진행할 수 있습니다.")
        if self.version != CONSENT_VERSION:
            raise ValueError("동의서 버전이 최신이 아닙니다. 다시 확인해 주세요.")
        return self
