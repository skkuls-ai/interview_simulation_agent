"""서류 분석(새 계약) smoke test + 정답 라벨 채점 (담당 A, W-15).

    python -m scripts.proof_prep_smoke
    python -m scripts.proof_prep_smoke --model gemini-3.7-flash

데모 샘플(data/demo/sample_inputs.json)로 실제 Gemini 를 호출해 docs/04 의 Analysis 를 만들고,
정답 라벨(data/demo/expected_points.json)과 비교합니다. pytest 밖에 둔 이유: API 호출 시간과 할당량을 씁니다.

채점
- 주장 포착: 라벨 인용과 Claim.text 가 서로 포함 관계면 포착
- 검증 포인트 탐지: 라벨이 가리키는 주장들을 참조하는 검증 포인트가 있으면 탐지 (불일치 CP2 는 두 주장을 함께 참조해야 탐지)
- 요구사항 공백: 라벨 인용의 요구사항이 추출됐고, 그 연결(RequirementLink.claim_ids)이 비어 있으면 탐지
- 함정: N1 (4인 팀 ↔ 3명의 팀원) 을 인원 불일치로 만들었는지, N2 를 검증 포인트로 만들었는지 → 사람이 최종 확인
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import time
from datetime import datetime
from pathlib import Path

from backend.llm.client import GeminiClient
from backend.llm.settings import LLMSettings
from backend.proof_prep.analysis import run_analysis
from backend.proof_prep.quotes import find_quote

ROOT = Path(__file__).parents[1]
DEMO = ROOT / "data" / "demo"


def overlaps(a: str, b: str) -> bool:
    return bool(find_quote(a, b, min_chars=4) or find_quote(b, a, min_chars=4))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", help="analysis 역할 모델 덮어쓰기")
    args = ap.parse_args()
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
    logging.getLogger("google_genai.models").setLevel(logging.ERROR)  # AFC 안내 로그 숨김
    if args.model:
        os.environ["INTERVIEW_MODEL_ANALYSIS"] = args.model

    settings = LLMSettings.from_env()
    inputs = json.loads((DEMO / "sample_inputs.json").read_text(encoding="utf-8"))
    labels = json.loads((DEMO / "expected_points.json").read_text(encoding="utf-8"))

    print(f"모델: {settings.role('analysis').model}\n")
    events: list[tuple[float, str, str, str | None]] = []
    t0 = time.perf_counter()
    rep = run_analysis(
        GeminiClient(settings),
        inputs["resume_text"], inputs["job_posting_text"], inputs["job_description_text"], inputs["cover_letter_text"],
        on_step=lambda s, state, d: events.append((time.perf_counter() - t0, s, state, d)),
    )
    wall = time.perf_counter() - t0
    a = rep.analysis

    # ------------------------------------------------------------ 결과
    print("=== 단계 진행 (화면 3)")
    for t, s, state, d in events:
        if state == "DONE":
            print(f"  {t:5.1f}초  {s:13} {d or ''}")
    print(f"\n=== 요구사항 {len(a.requirements)}개")
    linked = {l.requirement_id: l.claim_ids for l in a.links}
    for r in a.requirements:
        mark = "·" if linked.get(r.requirement_id) else "∅"
        print(f"  {mark} {r.requirement_id} [{r.source_doc:15} {r.kind:6}] {r.text}  → {linked.get(r.requirement_id)}")
    print(f"\n=== 주장 {len(a.claims)}개 (경험 {rep.experience_count}개)")
    for c in a.claims:
        print(f"  {c.claim_id} [{c.source_doc:12}] ({'/'.join(c.types)}) {c.text}")
    print(f"\n=== 검증 포인트 {len(a.checkpoints)}개")
    for cp in a.checkpoints:
        print(f"  {cp.checkpoint_id} {cp.title}  {cp.claim_ids}\n         {cp.what_to_verify}")

    # ------------------------------------------------------------ 채점
    print("\n=== 채점: 주장 포착")
    label_to_claims: dict[str, list[str]] = {}
    for lab in labels["expected_claims"]:
        hits = [c.claim_id for c in a.claims if c.source_doc == lab["source_doc"] and overlaps(lab["quote"], c.text)]
        label_to_claims[lab["label_id"]] = hits
        print(f"  {'✅' if hits else '✗'} {lab['label_id']:4} {lab['quote'][:40]:42} → {hits}")
    claim_hit = sum(bool(v) for v in label_to_claims.values())

    print("\n=== 채점: 검증 포인트 탐지")
    cp_hit = 0
    for lab in labels["expected_checkpoints"]:
        groups = [set(label_to_claims[cid]) for cid in lab["claim_label_ids"]]
        need_all = lab["label_id"] == "CP2"  # 서류 간 불일치는 두 주장을 함께 봐야 함
        found = [cp.checkpoint_id for cp in a.checkpoints
                 if (all(g & set(cp.claim_ids) for g in groups) if need_all else any(g & set(cp.claim_ids) for g in groups))]
        cp_hit += bool(found)
        print(f"  {'✅' if found else '✗'} {lab['label_id']} [{lab['priority']:6}] {lab['title']:20} → {found}")

    print("\n=== 채점: 요구사항 공백")
    gap_hit = 0
    for lab in labels["expected_gaps"]:
        rids = [rid for rid, q in rep.requirement_quotes.items() if overlaps(lab["quote"], q)]
        empty = [rid for rid in rids if not linked.get(rid)]
        gap_hit += bool(empty)
        state = "✅ 공백으로 표시" if empty else ("✗ 추출됐지만 연결됨" if rids else "✗ 요구사항 미추출")
        print(f"  {state:14} {lab['label_id']} [{lab['priority']:6}] {lab['quote']} → {rids}")

    print("\n=== 함정 (사람 확인)")
    n1 = [cp for cp in a.checkpoints if re.search(r"인원|팀원 ?수|팀 ?규모|몇 ?명", cp.title + cp.what_to_verify)]
    print(f"  N1 인원 불일치 오탐 후보: {[f'{cp.checkpoint_id} {cp.title}' for cp in n1] or '없음 ✅'}")
    n2_quote = labels["traps"][1]["sources"][0]["quote"]
    n2_ids = {c.claim_id for c in a.claims if overlaps(n2_quote, c.text)}
    n2 = [cp for cp in a.checkpoints if n2_ids & set(cp.claim_ids)]
    print(f"  N2 과잉 탐지 후보: {[f'{cp.checkpoint_id} {cp.title}' for cp in n2] or '없음 ✅'}")

    print(f"\n=== 요약")
    print(f"  주장 포착        {claim_hit}/{len(labels['expected_claims'])}")
    print(f"  검증 포인트 탐지  {cp_hit}/{len(labels['expected_checkpoints'])}")
    print(f"  요구사항 공백     {gap_hit}/{len(labels['expected_gaps'])}")
    print(f"  대체값 사용 단계  {rep.fallbacks or '없음'}")
    print(f"  안전장치 발동     {sum(len(v) for v in rep.issues.values())}건")
    print(f"  전체 소요         {wall:.1f}초 (목표 20~40초, 60초 초과 시 다시 시도)")

    out = ROOT / "var" / "eval" / f"proof_prep_{datetime.now():%Y%m%d_%H%M%S}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({
        "model": settings.role("analysis").model, "wall_sec": round(wall, 1),
        "analysis": a.model_dump(), "experience_count": rep.experience_count,
        "requirement_quotes": rep.requirement_quotes, "issues": rep.issues, "fallbacks": rep.fallbacks,
        "score": {"claims": claim_hit, "checkpoints": cp_hit, "gaps": gap_hit},
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  기록              {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
