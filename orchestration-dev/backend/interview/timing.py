"""답변 시간 예산과 장황한 답변 리포트. LLM 없이 코드로 계산합니다."""

from __future__ import annotations

from .blueprint import CATEGORY_NAMES
from .state import OvertimeAnswer, QuestionThread, SessionConfig, TimeReport


def fmt(sec: float) -> str:
    sec = int(round(sec))
    m, s = divmod(sec, 60)
    if m and s:
        return f"{m}분 {s}초"
    return f"{m}분" if m else f"{s}초"


def _short(text: str, n: int = 28) -> str:
    return text if len(text) <= n else text[:n].rstrip() + "…"


def overtime_of(duration_sec: float, config: SessionConfig) -> float:
    return max(0.0, duration_sec - config.answer_soft_limit_sec)


def build_time_report(
    threads: list[QuestionThread], config: SessionConfig, used_sec: float, unasked_categories: list[str],
    cut_categories: dict[str, int] | None = None,
) -> TimeReport:
    cut_categories = cut_categories or {}
    budget = config.answer_budget_min * 60
    overtime: list[OvertimeAnswer] = []
    for th in threads:
        question_text = ""
        for t in th.turns:
            if t.speaker == "interviewer":
                question_text = t.text
            elif t.overtime_sec and t.overtime_sec > 0:
                overtime.append(
                    OvertimeAnswer(
                        thread_id=th.thread_id, stage=th.stage, question_text=question_text,
                        duration_sec=t.answer_duration_sec or 0, overtime_sec=t.overtime_sec,
                    )
                )
    overtime.sort(key=lambda o: o.overtime_sec, reverse=True)
    exhausted = used_sec >= budget

    msgs: list[str] = []
    if overtime:
        msgs.append(
            f"권장 답변 시간({fmt(config.answer_soft_limit_sec)})을 넘긴 답변이 {len(overtime)}개 있었습니다."
        )
        for o in overtime[:5]:
            msgs.append(f"'{_short(o.question_text)}' 답변: {fmt(o.duration_sec)} (초과 {fmt(o.overtime_sec)})")
    else:
        msgs.append("모든 답변이 권장 시간 안에 끝났습니다.")

    if cut_categories:
        cause = "답변이 장황해진 탓에" if overtime else "답변 시간이 누적되면서"
        names = ", ".join(CATEGORY_NAMES.get(c, c) for c in cut_categories)
        counts = ", ".join(f"{CATEGORY_NAMES.get(c, c)} {n}개" for c, n in cut_categories.items())
        msgs.append(
            f"전체 답변 시간이 기준({fmt(budget)})을 넘었습니다. {cause} {names} 질문을 할 시간이 없었습니다 "
            f"(드리지 못한 질문: {counts})."
        )
        if unasked_categories:
            names = ", ".join(CATEGORY_NAMES.get(c, c) for c in unasked_categories)
            msgs.append(f"{names}은 한 문항도 묻지 못해 평가 근거가 없는 상태로 끝났습니다.")
    elif exhausted:
        cut_follow_ups = any(th.close_reason == "budget_exhausted" for th in threads)
        msgs.append(
            f"전체 답변 시간이 기준({fmt(budget)})을 넘었습니다."
            + (" 그래서 일부 꼬리질문을 드리지 못했습니다." if cut_follow_ups else "")
        )

    if overtime or exhausted:
        msgs.append("결론과 본인의 행동을 먼저 말하고, 세부 배경은 꼬리질문에서 보충하는 방식으로 연습해 보세요.")

    return TimeReport(
        budget_sec=budget, total_answer_sec=round(used_sec, 1), budget_exhausted=exhausted,
        overtime_answers=overtime, unasked_categories=unasked_categories, cut_categories=cut_categories,
        messages=msgs,
    )
