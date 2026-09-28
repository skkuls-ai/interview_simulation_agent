from typing import Protocol

from google import genai
from google.genai import types


class STTService(Protocol):
    async def transcribe(self, audio: bytes, mime_type: str) -> str:
        ...


class MockSTTService:
    """팀 통합 및 API 테스트용. 실제 STT adapter로 교체한다."""

    async def transcribe(self, audio: bytes, mime_type: str) -> str:
        del audio, mime_type
        return "RAG 프로젝트에서 검색 파이프라인을 담당했습니다."


_TRANSCRIBE_PROMPT = (
    "다음 오디오에서 화자가 말한 내용을 한국어로 그대로 전사해줘. "
    "전사한 문장만 출력하고 설명, 따옴표, 마크다운은 붙이지 마."
)


class GeminiSTTService:
    """Gemini의 오디오 이해 기능으로 답변 음성을 텍스트로 변환한다.

    GEMINI_API_KEY 환경 변수가 필요하다. 앱 시작 시가 아니라
    첫 transcribe 호출 시점에 클라이언트를 만들어, 키가 없어도
    다른 엔드포인트나 테스트는 영향을 받지 않게 한다.
    """

    def __init__(self, model: str = "gemini-3.8-flash") -> None:
        self._model = model
        self._client: genai.Client | None = None

    def _client_or_create(self) -> genai.Client:
        if self._client is None:
            self._client = genai.Client()
        return self._client

    async def transcribe(self, audio: bytes, mime_type: str) -> str:
        response = await self._client_or_create().aio.models.generate_content(
            model=self._model,
            contents=[
                types.Part.from_bytes(data=audio, mime_type=mime_type),
                _TRANSCRIBE_PROMPT,
            ],
        )
        return (response.text or "").strip()

