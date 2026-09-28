"""체크포인트 직렬화 허용 목록.

LangGraph 는 등록되지 않은 타입을 체크포인트에서 복원할 때 경고를 내고, 향후 버전에서는 막습니다.
state, blueprint, events 모듈의 Pydantic 모델과 Enum 을 자동으로 등록합니다.
"""

from __future__ import annotations

import inspect
import sqlite3
from enum import Enum

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from pydantic import BaseModel

from . import blueprint, events, state

_MODULES = [state, blueprint, events]


def make_serializer() -> JsonPlusSerializer:
    allowed = [
        (m.__name__, name)
        for m in _MODULES
        for name, obj in vars(m).items()
        # 다른 모듈에서 옮겨 와 다시 공개한 클래스도 허용 (예: state.VerificationPoint → blueprint 로 이동).
        # 옮기기 전에 저장된 세션을 이어갈 때 필요
        if inspect.isclass(obj) and obj.__module__.startswith("backend.") and issubclass(obj, (BaseModel, Enum))
    ]
    return JsonPlusSerializer(allowed_msgpack_modules=allowed)


def make_memory_checkpointer() -> InMemorySaver:
    """테스트용. 프로세스가 끝나면 사라집니다."""
    return InMemorySaver(serde=make_serializer())


def make_sqlite_checkpointer(path: str):
    """운영용. 서버를 재시작해도 세션을 이어갈 수 있습니다."""
    from langgraph.checkpoint.sqlite import SqliteSaver

    conn = sqlite3.connect(path, check_same_thread=False)
    return SqliteSaver(conn, serde=make_serializer())
