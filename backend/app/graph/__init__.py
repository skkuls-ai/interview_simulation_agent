"""준비·평가 그래프 진입점. 모드에 따라 진짜 그래프(prepare, evaluate)나 가짜 진행기(fake)를 부른다."""
from ..store import Store
from . import evaluate, fake, prepare
from .llm_factory import graph_mode


def run_prepare(store: Store, session_id: str) -> None:
    if graph_mode() == "fake":
        return fake.run_prepare(store, session_id)
    return prepare.run_prepare(store, session_id)


def run_evaluate(store: Store, session_id: str) -> None:
    if graph_mode() == "fake":
        return fake.run_evaluate(store, session_id)
    return evaluate.run_evaluate(store, session_id)


__all__ = ["run_evaluate", "run_prepare"]
