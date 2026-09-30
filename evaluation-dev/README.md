# evaluation-dev (담당 E, 임시 폴더)

C의 저장소 뼈대(W-02, W-03)가 올라오기 전까지 쓰는 E(피드백) 작업 폴더다. 뼈대가 올라오면 파일을 제자리로 옮겨 PR을 보낸다.

| 지금 | 옮길 곳 | 내용 |
| --- | --- | --- |
| `mock/report.json`, `mock/report_edge.json` | `shared/mock/` (C 리뷰) | 화면 7용 `GET /report` 응답 mock (W-14) |
| `mock/build_report_mock.py` | `shared/mock/` 또는 `scripts/` | mock 생성과 계약 검사 |

자세한 내용은 [mock/README.md](mock/README.md).
