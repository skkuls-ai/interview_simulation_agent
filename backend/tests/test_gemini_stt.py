import os
import tempfile
from types import SimpleNamespace

import pytest

from app.audio import transcribe_and_delete
from app.audio.gemini_stt import GeminiStt
from app.audio.stt import StubStt, get_stt, stt_mode
from app.schemas.state import Answer, TranscriptStatus
from app.store import Store


class FakeModels:
    def __init__(self, text=None, error=None):
        self.text, self.error, self.calls = text, error, []

    def generate_content(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return SimpleNamespace(text=self.text)


def fake_client(**kw):
    models = FakeModels(**kw)
    return SimpleNamespace(models=models), models


def audio_file(data=b"webm-bytes"):
    fd, path = tempfile.mkstemp(suffix=".webm")
    with os.fdopen(fd, "wb") as f:
        f.write(data)
    return path


def run(stt, data=b"webm-bytes"):
    store = Store()
    rec = store.create(resume_text="a", job_posting_text="b", job_description_text="c", cover_letter_text="d")
    sid = rec.state.session_id
    rec.state.answers.append(Answer(question_id="Q-1", duration_sec=10))
    path = audio_file(data)
    transcribe_and_delete(store, sid, "Q-1", path, stt)
    assert not os.path.exists(path)
    return rec.state.answers[0]


def test_done_keeps_fillers_and_sends_audio():
    client, models = fake_client(text="  어 안녕하세요 음 저는  ")
    a = run(GeminiStt(client=client, model="m"))
    assert (a.transcript_status, a.transcript) == (TranscriptStatus.DONE, "어 안녕하세요 음 저는")
    call = models.calls[0]
    assert call["model"] == "m"
    assert call["contents"][0].inline_data.mime_type == "audio/webm"


def test_empty_response_is_no_speech():
    client, _ = fake_client(text="")
    a = run(GeminiStt(client=client))
    assert (a.transcript_status, a.transcript) == (TranscriptStatus.NO_SPEECH, None)


def test_empty_file_skips_call():
    client, models = fake_client(text="x")
    a = run(GeminiStt(client=client), data=b"")
    assert a.transcript_status == TranscriptStatus.NO_SPEECH and models.calls == []


def test_error_is_failed_without_leaking_text():
    client, _ = fake_client(error=RuntimeError("503"))
    a = run(GeminiStt(client=client))
    assert (a.transcript_status, a.transcript) == (TranscriptStatus.FAILED, None)


def test_mode_selection(monkeypatch):
    monkeypatch.setenv("STT_MODE", "stub")
    assert stt_mode() == "stub" and isinstance(get_stt(), StubStt)
    monkeypatch.setenv("STT_MODE", "gemini")
    assert stt_mode() == "gemini"
    monkeypatch.setenv("STT_MODE", "auto")
    monkeypatch.delenv("GOOGLE_CLOUD_PROJECT", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.setattr("app.llm.settings.LLMSettings.from_env", classmethod(lambda cls: cls()))
    assert stt_mode() == "stub"
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "p")
    monkeypatch.setattr("app.llm.settings.LLMSettings.from_env", classmethod(lambda cls: cls(project="p")))
    assert stt_mode() == "gemini"
