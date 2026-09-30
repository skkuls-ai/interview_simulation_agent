# 멀티 에이전트 면접 시뮬레이터: 오케스트레이션 (orchestration-dev)

LangGraph 로 면접 흐름(서류 분석, 질문, 꼬리질문, 평가, 최종 판정)과 에이전트들을 조율하는 백엔드입니다.
표정과 시선 감지는 `perception-dev`, 검증 기능은 `feature/validation` 브랜치에서 다룹니다.

## 폴더 구조

```
C:\interview_simulation_agent\orchestration-dev\
├─ .env                  ← 직접 만듦 (.env.example 복사). 키가 들어가므로 공유 금지
├─ .env.example
├─ .gitignore
├─ .vscode\              ← VS Code 실행, 테스트 설정
├─ requirements.txt
├─ README.md
├─ backend\
│  ├─ config.py          .env 읽기
│  ├─ api\               FastAPI (python -m backend.api)
│  ├─ service\           세션, 동의, 문서, 저장, 백그라운드 평가
│  ├─ interview\         LangGraph 그래프 2개, 에이전트, 프롬프트
│  ├─ llm\               Gemini 연결, 역할별 모델 설정
│  └─ question_bank\     질문 은행 JSON, 스키마, 변환 스크립트
├─ data\question_bank_150.xlsx   원본 질문 파일
├─ docs\screen_flow.md   화면 흐름 (React 단계용)
├─ scripts\              터미널 데모, 꼬리질문 평가
├─ tests\                자동 테스트
├─ var\                  실행하면 자동 생성 (DB, 업로드, 평가 기록)
└─ frontend\             (다음 단계에서 React 추가)
```

## 처음 설정 (PowerShell, 한 번만)

```powershell
cd C:\interview_simulation_agent\orchestration-dev
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1          # 막히면: Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
python -m pip install -U pip
pip install -r requirements.txt
copy .env.example .env                # 그다음 .env 를 열어 값 확인
python -m pytest -q tests -p no:warnings
```

## Gemini 연결 (학교 Vertex AI 프로젝트)

1. Google Cloud CLI 설치: https://cloud.google.com/sdk/docs/install
2. 학교 계정으로 로그인
   ```powershell
   gcloud auth application-default login
   gcloud auth application-default set-quota-project <학교 GCP 프로젝트 ID>
   ```
3. `.env` 에 `GOOGLE_CLOUD_PROJECT` 가 채워져 있으면 API 키 없이 연결됩니다 (`GEMINI_API_KEY` 는 비워 둠).

## 실행

| 목적 | 명령 | VS Code 실행 메뉴 (F5) |
|---|---|---|
| API 서버 | `python -m backend.api` → http://127.0.0.1:8000/docs | API 서버 |
| 터미널로 면접 체험 | `python -m scripts.demo_cli --llm` | 터미널 면접 데모 (Gemini) |
| 꼬리질문 판단 평가 | `python -m scripts.eval_follow_up_judge --repeat 3` | 꼬리질문 판단 평가 (Gemini) |
| 평가자 3명 패널 평가 | `python -m scripts.eval_panel --repeat 2` | 평가 패널 평가 (Gemini) |
| 질문 엑셀 수정 후 반영 | `python -m backend.question_bank.convert` | 질문 은행 다시 변환 |
| 테스트 | `python -m pytest -q tests -p no:warnings` | 테스트 탭 |
