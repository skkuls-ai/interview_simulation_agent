import os
import tempfile

from app.audio import transcribe_and_delete
from app.schemas.state import Answer, TranscriptStatus
from app.store import Store


def setup_store():
    store = Store()
    rec = store.create(resume_text="a", job_posting_text="b", job_description_text="c", cover_letter_text="d")
    sid = rec.state.session_id
    rec.state.answers.append(Answer(question_id="Q-1", duration_sec=10))
    return store, sid, rec


def tmp_audio():
    fd, path = tempfile.mkstemp(suffix=".webm")
    os.close(fd)
    return path


class Fixed:
    def __init__(self, value):
        self.value = value

    def transcribe(self, path):
        return self.value


class Boom:
    def transcribe(self, path):
        raise RuntimeError("stt down")


def check(stt, expected_status, expected_text):
    store, sid, rec = setup_store()
    path = tmp_audio()
    transcribe_and_delete(store, sid, "Q-1", path, stt)
    assert not os.path.exists(path)  # 성공·무음·실패 모두 파일 삭제
    a = rec.state.answers[0]
    assert a.transcript_status == expected_status and a.transcript == expected_text


def test_done():
    check(Fixed("안녕하세요"), TranscriptStatus.DONE, "안녕하세요")


def test_no_speech():
    check(Fixed("  "), TranscriptStatus.NO_SPEECH, None)


def test_failed():
    check(Boom(), TranscriptStatus.FAILED, None)


def test_no_audio_is_no_speech():
    store, sid, rec = setup_store()
    transcribe_and_delete(store, sid, "Q-1", None)
    assert rec.state.answers[0].transcript_status == TranscriptStatus.NO_SPEECH
