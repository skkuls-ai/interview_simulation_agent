"""분석 그래프: 문서 → 면접 설계도(InterviewBlueprint).

    START ─┬→ analyze_jd ──────────┬→ link → find_verification_points → plan_questions
           ├→ analyze_experiences ─┘                                      ↓
           └→ plan_questions (문서가 없으면)                validate_questions → build_rubric → assemble → END

- 검증 포인트는 여기서 주로 만들고, 면접 중 자기소개에서 새로 나온 주장만 추가합니다.
- 개인화한 질문은 검증 에이전트가 확인하고, 떨어지면 최대 2번 다시 개인화한 뒤 그래도 안 되면 원본 문구로 되돌립니다.

JD 만 있거나 이력서만 있어도 있는 만큼 분석합니다.
"""

from __future__ import annotations

import math
import random
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from ..question_bank.models import Question, QuestionBank, QuestionType
from .agents import AnalysisAgents
from .blueprint import (
    CATEGORY_NAMES,
    CategoryPlan,
    CompanyContext,
    Experience,
    GuideItem,
    InterviewBlueprint,
    InterviewGuide,
    IntroRubric,
    JDRequirement,
    PlannedQuestion,
    QuestionRubric,
    RequirementLink,
    Rubric,
    VerificationPoint,
)
from .guards import check_generated

MAX_PERSONALIZE_RETRIES = 2
from .state import SessionConfig
from .timing import fmt


class AnalysisState(TypedDict, total=False):
    config: SessionConfig
    target_role: str | None
    jd_text: str | None
    resume_text: str | None
    cover_letter_text: str | None
    seed: int | None

    company: CompanyContext
    requirements: list[JDRequirement]
    experiences: list[Experience]
    links: list[RequirementLink]
    verification_points: list[VerificationPoint]
    plan: list[CategoryPlan]
    question_rubrics: list[QuestionRubric]
    intro_rubric: IntroRubric
    blueprint: InterviewBlueprint


def has_documents(state: AnalysisState) -> bool:
    return any((state.get(k) or "").strip() for k in ("jd_text", "resume_text", "cover_letter_text"))


def rank_competencies(
    bank: QuestionBank, category_code: str, requirements: list[JDRequirement], experiences: list[Experience],
    rng: random.Random, boost: set[str] | None = None,
) -> list[str]:
    """JD 필수 요구 2점, 우대 1점, 관련 경험 1점, 검증 포인트 관련 1.5점. 동점은 무작위 (문서가 없으면 전부 무작위)."""
    cat = next(c for c in bank.categories if c.code == category_code)
    scored = []
    for comp in cat.competencies:
        s = sum(2 if r.importance == "must" else 1 for r in requirements if comp.code in r.competency_codes)
        s += sum(1 for e in experiences if comp.code in e.competency_codes)
        s += 1.5 if boost and comp.code in boost else 0
        scored.append((s, rng.random(), comp.code))
    return [code for _, _, code in sorted(scored, reverse=True)]


def pick_question(bank: QuestionBank, competency_code: str, rng: random.Random, behavioral_first: bool) -> Question:
    qs = bank.by_competency(competency_code)
    if behavioral_first:
        beh = [q for q in qs if q.question_type is QuestionType.BEHAVIORAL]
        qs = beh or qs
    return rng.choice(qs)


def estimate_minutes(config: SessionConfig) -> tuple[int, int]:
    """예상 소요 시간. 질문 읽기와 준비시간(질문당 약 17초)을 포함한 범위."""
    n_main = config.questions_per_category * len(config.category_order)
    overhead_per_prompt_min = (config.think_time_sec + 12) / 60
    typical_answers = 1 + n_main * (1 + 2 * 0.75) + 0.5
    typical_prompts = 1 + n_main * 3 + 1
    low = typical_answers + typical_prompts * overhead_per_prompt_min
    max_prompts = 1 + n_main * (1 + config.max_follow_ups) + 1
    high = config.answer_budget_min + max_prompts * overhead_per_prompt_min
    return int(5 * round(low / 5)), int(5 * math.ceil(high / 5))


def build_guide(config: SessionConfig, personalized: bool) -> InterviewGuide:
    n_main = config.questions_per_category * len(config.category_order)
    topics = ", ".join(CATEGORY_NAMES[c].replace("역량", "") for c in config.category_order)
    return InterviewGuide(
        items=[
            GuideItem(topic="자기소개", count=1, note="1분 내외"),
            GuideItem(
                topic=f"{topics} 역량에 관한 경험과 상황 질문",
                count=n_main,
                note=(
                    f"답변에 따라 꼬리질문이 이어지고, 필요하면 영역별로 {config.max_extra_per_category}문항이 추가될 수 있습니다"
                    + (". 제출하신 서류를 바탕으로 질문을 구성했습니다" if personalized else "")
                ),
            ),
            GuideItem(topic="마무리", count=1, note="하고 싶은 말씀 (평가에는 반영되지 않습니다)"),
        ],
        expected_minutes=estimate_minutes(config),
        answer_rules=[
            f"질문이 끝나면 {config.think_time_sec}초 준비시간 후 답변시간이 시작됩니다.",
            f"답변은 {fmt(config.answer_soft_limit_sec)} 내외를 권장합니다. 넘으면 화면에 초과 시간이 표시되지만 답변은 끊기지 않습니다.",
            "답변이 끝나면 '답변 완료' 버튼을 눌러 주세요.",
            f"답변 시간 합계가 기준({fmt(config.answer_budget_min * 60)})을 넘으면 남은 질문을 드리지 못하고 면접이 마무리됩니다.",
        ],
    )


def build_analysis_graph(bank: QuestionBank, agents: AnalysisAgents, checkpointer=None):
    def route_start(state: AnalysisState):
        if not has_documents(state):
            return ["plan_questions"]
        routes = []
        if (state.get("jd_text") or "").strip():
            routes.append("analyze_jd")
        if (state.get("resume_text") or "").strip() or (state.get("cover_letter_text") or "").strip():
            routes.append("analyze_experiences")
        return routes

    def analyze_jd(state: AnalysisState) -> dict:
        company, reqs = agents.analyze_jd(state["jd_text"])
        if state.get("target_role") and not company.role_title:
            company = company.model_copy(update={"role_title": state["target_role"]})
        return {"company": company, "requirements": reqs}

    def analyze_experiences(state: AnalysisState) -> dict:
        return {"experiences": agents.analyze_experiences(state.get("resume_text"), state.get("cover_letter_text"))}

    def link(state: AnalysisState) -> dict:
        reqs, exps = state.get("requirements", []), state.get("experiences", [])
        return {"links": agents.link(reqs, exps) if reqs and exps else []}

    def point_competencies(p: VerificationPoint, reqs, exps) -> set[str]:
        codes = {c for r in reqs if r.id in p.requirement_ids for c in r.competency_codes}
        codes |= {c for e in exps if e.id in p.experience_ids for c in e.competency_codes}
        return codes

    def categories_of(codes: set[str]) -> list[str]:
        return [c.code for c in bank.categories if any(x.code in codes for x in c.competencies)]

    def find_verification_points(state: AnalysisState) -> dict:
        reqs, exps = state.get("requirements", []), state.get("experiences", [])
        points = agents.verification_points(state.get("company", CompanyContext()), reqs, exps, state.get("links", []))
        valid_cats = set(state["config"].category_order)
        fixed = []
        for i, p in enumerate(points, 1):
            # LLM 이 영역 코드를 잘못 쓰면(예: "성과역량", 소분류 코드) 포인트가 어느 질문에도 연결되지 않으므로 보정
            cats = [c for c in p.category_codes if c in valid_cats]
            cats = cats or [c for c in categories_of(point_competencies(p, reqs, exps)) if c in valid_cats] or ["performance"]
            fixed.append(p.model_copy(update={"id": f"V{i}", "source": "documents", "category_codes": cats}))
        return {"verification_points": fixed}

    def plan_questions(state: AnalysisState) -> dict:
        cfg = state["config"]
        rng = random.Random(state.get("seed"))
        reqs, exps = state.get("requirements", []), state.get("experiences", [])
        points = state.get("verification_points", [])
        boost = set().union(*[point_competencies(p, reqs, exps) for p in points]) if points else set()
        personalized = has_documents(state)
        plan = []
        for cat in cfg.category_order:
            ranked = rank_competencies(bank, cat, reqs, exps, rng, boost)
            n_primary, n_reserve = cfg.questions_per_category, cfg.max_extra_per_category
            picks = []
            for i, comp in enumerate(ranked[: n_primary + n_reserve]):
                q = pick_question(bank, comp, rng, behavioral_first=i < n_primary)
                pq = PlannedQuestion(
                    question_id=q.id, category_code=cat, competency_code=comp,
                    target_requirement_ids=[r.id for r in reqs if comp in r.competency_codes],
                    reason="JD 요구사항과 경험 연관도 순" if personalized else "문항 은행 무작위 선정",
                )
                if personalized and exps:
                    pq = agents.personalize(q, pq, exps, reqs)
                picks.append(pq)
            plan.append(CategoryPlan(category_code=cat, primary=picks[:n_primary], reserve=picks[n_primary:]))
        return {"plan": assign_points(plan, points, reqs, exps)}

    def assign_points(plan, points, reqs, exps):
        """검증 포인트마다 확인하기 좋은 기본 문항을 하나 정해 둡니다 (관련 역량 우선, 없으면 그 영역 첫 문항)."""
        by_q: dict[str, list[str]] = {}
        for p in points:
            comps = point_competencies(p, reqs, exps)
            candidates = [pq for cp in plan if cp.category_code in p.category_codes for pq in cp.primary]
            if not candidates:
                continue
            target = next((pq for pq in candidates if pq.competency_code in comps), candidates[0])
            by_q.setdefault(target.question_id, []).append(p.id)
        return [
            cp.model_copy(update={
                "primary": [pq.model_copy(update={"verification_point_ids": by_q.get(pq.question_id, [])}) for pq in cp.primary]
            })
            for cp in plan
        ]

    def validate_questions(state: AnalysisState) -> dict:
        reqs, exps = state.get("requirements", []), state.get("experiences", [])
        new_plan = []
        for cp in state["plan"]:
            fixed = {}
            for kind in ("primary", "reserve"):
                out = []
                for pq in getattr(cp, kind):
                    out.append(_validate_one(pq, reqs, exps))
                fixed[kind] = out
            new_plan.append(cp.model_copy(update=fixed))
        return {"plan": new_plan}

    def _validate_one(pq: PlannedQuestion, reqs, exps) -> PlannedQuestion:
        if not pq.personalized_text:
            return pq
        q = bank.get(pq.question_id)
        notes: list[str] = []
        current = pq
        for attempt in range(MAX_PERSONALIZE_RETRIES + 1):
            problem = check_generated(current.personalized_text or "", max_chars=400)
            if problem:
                issues = [problem]
            else:
                v = agents.validate_question(q, current, exps, reqs)
                issues = [] if v.passed else (v.issues or ["검증 실패"])
            if not issues:
                return current.model_copy(update={"validation": "passed", "validation_notes": notes})
            notes.append(f"{attempt + 1}차 검증 실패: {'; '.join(issues)}")
            if attempt < MAX_PERSONALIZE_RETRIES:
                again = agents.personalize(q, pq.model_copy(update={"personalized_text": None}), exps, reqs, feedback=issues)
                # 문구 관련 칸만 가져옴 (검증 포인트 배정 등 계획 정보는 유지)
                current = pq.model_copy(update={"personalized_text": again.personalized_text,
                                                "anchor_experience_id": again.anchor_experience_id})
                if not current.personalized_text:
                    break
        return pq.model_copy(update={"personalized_text": None, "anchor_experience_id": None,
                                     "validation": "reverted", "validation_notes": notes + ["원본 문구로 되돌림"]})

    def build_rubric(state: AnalysisState) -> dict:
        reqs = state.get("requirements", [])
        qrs = [
            agents.question_rubric(bank.get(pq.question_id), reqs)
            for cp in state["plan"] for pq in cp.primary + cp.reserve
        ]
        company = state.get("company", CompanyContext())
        intro = agents.intro_rubric(company, reqs, state.get("links", []))
        return {"question_rubrics": qrs, "intro_rubric": intro}

    def assemble(state: AnalysisState) -> dict:
        personalized = has_documents(state)
        bp = InterviewBlueprint(
            personalized=personalized,
            target_role=state.get("target_role"),
            company=state.get("company", CompanyContext()),
            requirements=state.get("requirements", []),
            experiences=state.get("experiences", []),
            links=state.get("links", []),
            verification_points=state.get("verification_points", []),
            plan=state["plan"],
            rubric=Rubric(questions=state["question_rubrics"], intro=state["intro_rubric"]),
            guide=build_guide(state["config"], personalized),
        )
        return {"blueprint": bp}

    g = StateGraph(AnalysisState)
    for name, fn in [("analyze_jd", analyze_jd), ("analyze_experiences", analyze_experiences), ("link", link),
                     ("find_verification_points", find_verification_points), ("plan_questions", plan_questions),
                     ("validate_questions", validate_questions), ("build_rubric", build_rubric), ("assemble", assemble)]:
        g.add_node(name, fn)
    g.add_conditional_edges(START, route_start, ["analyze_jd", "analyze_experiences", "plan_questions"])
    g.add_edge("analyze_jd", "link")
    g.add_edge("analyze_experiences", "link")
    g.add_edge("link", "find_verification_points")
    g.add_edge("find_verification_points", "plan_questions")
    g.add_edge("plan_questions", "validate_questions")
    g.add_edge("validate_questions", "build_rubric")
    g.add_edge("build_rubric", "assemble")
    g.add_edge("assemble", END)
    return g.compile(checkpointer=checkpointer)
