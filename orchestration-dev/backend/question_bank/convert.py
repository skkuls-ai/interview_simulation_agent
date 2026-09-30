"""엑셀 질문 파일을 question_bank.json 과 schema.json 으로 변환합니다.

사용법 (프로젝트 루트에서):
    python -m backend.question_bank.convert            (기본: data/question_bank_150.xlsx)

필요 패키지: pandas, openpyxl, pydantic>=2
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

import pandas as pd

from .models import (
    QUESTION_TYPE_LABELS,
    Category,
    Checkpoint,
    Checkpoints,
    Competency,
    FollowUp,
    FollowUpKind,
    Intent,
    Question,
    QuestionBank,
    QuestionType,
)

HERE = Path(__file__).parent

COLUMNS = [
    "No", "대분류", "소분류", "소분류 설명", "질문유형", "질문",
    "추가 질문", "질문 의도", "Positive 체크포인트", "Negative 체크포인트",
]

CATEGORY_CODES = {
    "성과역량": "performance",
    "관계역량": "relationship",
    "리더십역량": "leadership",
    "적응역량": "adaptability",
}

COMPETENCY_CODES = {
    # 성과역량
    "긍정성": "positivity",
    "기획력": "planning",
    "끈기": "persistence",
    "문제해결력": "problem_solving",
    "성과관리력": "performance_management",
    "성실성": "diligence",
    "성취갈망": "achievement_drive",
    "실행력": "execution",
    "열정": "passion",
    "전문분야 지식/기술": "expertise",
    "정보관리력": "information_management",
    "창의력": "creativity",
    # 관계역량
    "고객지향성": "customer_orientation",
    "능동성": "proactiveness",
    "설득력": "persuasion",
    "유연성": "flexibility",
    "의사소통력": "communication",
    "협력성": "collaboration",
    "협상력": "negotiation",
    # 리더십역량
    "변화촉진력": "change_facilitation",
    "비전제시력": "vision_setting",
    "업무위임력": "delegation",
    "의사결정력": "decision_making",
    "조직계발력": "organization_development",
    "통합조정력": "coordination",
    # 적응역량
    "규범성": "rule_compliance",
    "모범성": "role_modeling",
    "스트레스 내성": "stress_tolerance",
    "스트레스 복원력": "stress_resilience",
    "책임감": "responsibility",
}

TYPE_BY_LABEL = {label: t for t, label in QUESTION_TYPE_LABELS.items()}

_NUMBERED = re.compile(r"^\s*(\d+)\.\s*(.+?)\s*$")
_CIRCLED = re.compile(r"^\s*([①②③④⑤⑥⑦⑧⑨⑩])\s*(.+?)\s*$")
_BULLET = re.compile(r"^\s*-\s*(.+?)\s*$")
_PAREN_PREFIX = re.compile(r"^\(([^)]+)\)\s*(.+)$")
_FALLBACK = re.compile(r"\s*\((?:답변하지 못할 경우|답변을 못할 경우)\)\s*(.+)$")


def clean(text: str) -> str:
    """공백 정리와 명백한 오타(물음표 중복)만 고칩니다. 내용은 바꾸지 않습니다."""
    text = re.sub(r"\s+", " ", str(text)).strip()
    return re.sub(r"\?{2,}", "?", text)


def split_lines(cell: str, pattern: re.Pattern, what: str, qno: int) -> list[re.Match]:
    matches = []
    for line in str(cell).splitlines():
        if not line.strip():
            continue
        m = pattern.match(line)
        if not m:
            raise ValueError(f"No {qno} {what}: 형식이 다른 줄 {line!r}")
        matches.append(m)
    return matches


def classify_paren(note: str) -> FollowUpKind | None:
    if "압박" in note:
        return FollowUpKind.PRESSURE
    if note.startswith("제가") and "생각하고" in note:
        return FollowUpKind.ROLE_PLAY
    if re.search(r"(다면|경우|때)$", note):
        return FollowUpKind.CONDITION
    return None  # 예: (앞서 질문한) 은 문장의 일부이므로 원문 유지


def parse_follow_ups(cell: str, qid: str, qno: int) -> list[FollowUp]:
    items = []
    for i, m in enumerate(split_lines(cell, _NUMBERED, "추가 질문", qno), start=1):
        raw = m.group(2).strip()
        text, kind, note = raw, None, None
        p = _PAREN_PREFIX.match(raw)
        if p and (k := classify_paren(p.group(1).strip())):
            kind, note, text = k, p.group(1).strip(), p.group(2)
        items.append(
            FollowUp(
                id=f"{qid}-F{i}", order=int(m.group(1)), text=clean(text),
                kind=kind, note=note, raw_text=raw,
            )
        )
    return items


def parse_row(row: pd.Series) -> Question:
    no = int(row["No"])
    qid = f"Q{no:03d}"
    intents = [
        Intent(id=f"{qid}-I{i}", text=clean(m.group(2)))
        for i, m in enumerate(split_lines(row["질문 의도"], _CIRCLED, "질문 의도", no), start=1)
    ]
    pos = [
        Checkpoint(id=f"{qid}-P{i}", text=clean(m.group(1)))
        for i, m in enumerate(split_lines(row["Positive 체크포인트"], _BULLET, "Positive", no), start=1)
    ]
    neg = [
        Checkpoint(id=f"{qid}-N{i}", text=clean(m.group(1)))
        for i, m in enumerate(split_lines(row["Negative 체크포인트"], _BULLET, "Negative", no), start=1)
    ]
    qtype = TYPE_BY_LABEL[row["질문유형"].strip()]
    text, fallback = clean(row["질문"]), None
    if m := _FALLBACK.search(text):
        text, fallback = text[: m.start()].strip(), m.group(1).strip()
    return Question(
        id=qid,
        no=no,
        category_code=CATEGORY_CODES[row["대분류"].strip()],
        category_name=row["대분류"].strip(),
        competency_code=COMPETENCY_CODES[row["소분류"].strip()],
        competency_name=row["소분류"].strip(),
        question_type=qtype,
        question_type_label=QUESTION_TYPE_LABELS[qtype],
        text=text,
        fallback_text=fallback,
        follow_ups=parse_follow_ups(row["추가 질문"], qid, no),
        intents=intents,
        checkpoints=Checkpoints(positive=pos, negative=neg),
    )


def flag_quality(questions: list[Question]) -> tuple[list[Question], list[str]]:
    """원본 데이터 문제를 표시합니다. 내용은 고치지 않고 플래그만 붙입니다."""
    warnings: list[str] = []
    first_by_content: dict[tuple, Question] = {}
    first_by_follow_ups: dict[tuple, Question] = {}
    out = []
    for q in questions:
        content = (q.text, tuple(i.text for i in q.intents), tuple(c.text for c in q.checkpoints.positive))
        fus = tuple(f.text for f in q.follow_ups)
        update = {}
        if content in first_by_content:
            orig = first_by_content[content]
            update["duplicate_of"] = orig.id
            same_comp = "같은 소분류" if orig.competency_code == q.competency_code else f"다른 소분류({orig.competency_name})"
            warnings.append(f"{q.id}: {orig.id} 문항과 질문, 의도, 체크포인트가 모두 같음 ({same_comp}). 선정에서 제외")
        elif fus in first_by_follow_ups:
            orig = first_by_follow_ups[fus]
            update["follow_ups_shared_with"] = orig.id
            warnings.append(f"{q.id}: 추가 질문 목록을 {orig.id} 문항과 공유 (검토 결과 사용). 맥락에 맞는 것만 골라 씀")
        first_by_content.setdefault(content, q)
        first_by_follow_ups.setdefault(fus, q)
        if q.fallback_text:
            warnings.append(f"{q.id}: 질문 안의 '(답변하지 못할 경우)' 안내를 fallback_text 로 분리")
        out.append(q.model_copy(update=update) if update else q)
    return out, warnings


def build_bank(xlsx: Path) -> QuestionBank:
    df = pd.read_excel(xlsx, dtype=str).fillna("")
    missing = [c for c in COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"엑셀에 없는 열: {missing}")

    questions = [parse_row(r) for _, r in df.iterrows()]
    questions.sort(key=lambda q: q.no)
    questions, warnings = flag_quality(questions)

    # 대분류와 소분류는 엑셀에 처음 등장한 순서 유지
    categories: list[Category] = []
    for cat_name in dict.fromkeys(df["대분류"].str.strip()):
        sub = df[df["대분류"].str.strip() == cat_name]
        comps = []
        for comp_name in dict.fromkeys(sub["소분류"].str.strip()):
            rows = sub[sub["소분류"].str.strip() == comp_name]
            descs = set(rows["소분류 설명"].map(clean))
            if len(descs) != 1:
                raise ValueError(f"{comp_name}: 소분류 설명이 여러 개 {descs}")
            comps.append(
                Competency(
                    code=COMPETENCY_CODES[comp_name],
                    name=comp_name,
                    description=descs.pop(),
                    question_ids=[f"Q{int(n):03d}" for n in rows["No"]],
                )
            )
        categories.append(Category(code=CATEGORY_CODES[cat_name], name=cat_name, competencies=comps))

    return QuestionBank(
        source_file=xlsx.name,
        source_sha256=hashlib.sha256(xlsx.read_bytes()).hexdigest(),
        categories=categories,
        questions=questions,
        quality_warnings=warnings,
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("xlsx", type=Path, nargs="?", default=HERE.parents[1] / "data" / "question_bank_150.xlsx")
    ap.add_argument("--out-dir", type=Path, default=HERE)
    args = ap.parse_args()

    bank = build_bank(args.xlsx)
    args.out_dir.mkdir(parents=True, exist_ok=True)

    (args.out_dir / "question_bank.json").write_text(
        bank.model_dump_json(indent=2, exclude_none=True), encoding="utf-8"
    )
    schema = QuestionBank.model_json_schema()
    schema = {"$schema": "https://json-schema.org/draft/2020-12/schema", "title": "QuestionBank", **schema}
    (args.out_dir / "schema.json").write_text(
        json.dumps(schema, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    n_fu = sum(len(q.follow_ups) for q in bank.questions)
    tagged = sum(1 for q in bank.questions for f in q.follow_ups if f.kind)
    print(f"질문 {len(bank.questions)}개, 꼬리질문 {n_fu}개 (괄호 표기 {tagged}개)")
    for c in bank.categories:
        print(f"  {c.name}: 소분류 {len(c.competencies)}개, 질문 {sum(len(x.question_ids) for x in c.competencies)}개")
    if bank.quality_warnings:
        print(f"원본 데이터 점검 {len(bank.quality_warnings)}건:")
        for w in bank.quality_warnings:
            print(f"  - {w}")
    print(f"저장: {args.out_dir / 'question_bank.json'}, {args.out_dir / 'schema.json'}")


if __name__ == "__main__":
    main()
