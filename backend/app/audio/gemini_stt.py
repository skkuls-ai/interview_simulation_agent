"""Gemini 오디오 입력으로 답변 녹음을 글자로 옮긴다 (Vertex AI, app/llm과 같은 연결).

변환 텍스트와 음성은 로그·예외 문구에 넣지 않는다 (07 규칙). 실패하면 예외를 그대로 올려
transcribe_and_delete가 FAILED로 기록하고 파일을 지운다.
"""
import os

STT_TIMEOUT_SEC = 25.0
DEFAULT_STT_MODEL = "gemini-3.8-flash"

PROMPT = (
    "이 녹음은 한국어 면접 답변이다. 들린 그대로 받아 적어라. "
    "「어」「음」「그」 같은 군말과 말 더듬도 지우지 말고, 내용을 고치거나 요약하거나 덧붙이지 마라. "
    "말소리가 없거나 알아들을 수 없으면 아무것도 출력하지 마라. 받아 적은 글만 출력하라."
)


class GeminiStt:
    def __init__(self, client=None, model: str | None = None, timeout_sec: float = STT_TIMEOUT_SEC):
        self._client = client
        self.model = model or os.environ.get("STT_MODEL") or DEFAULT_STT_MODEL
        self.timeout_sec = timeout_sec

    def _genai(self):
        if self._client is None:
            from ..graph.llm_factory import get_llm

            self._client = get_llm().client
        return self._client

    def transcribe(self, path: str) -> str | None:
        from google.genai import types

        with open(path, "rb") as f:
            data = f.read()
        if not data:
            return None
        resp = self._genai().models.generate_content(
            model=self.model,
            contents=[types.Part.from_bytes(data=data, mime_type="audio/webm"), PROMPT],
            config=types.GenerateContentConfig(
                http_options=types.HttpOptions(timeout=int(self.timeout_sec * 1000)),
            ),
        )
        return (resp.text or "").strip() or None
