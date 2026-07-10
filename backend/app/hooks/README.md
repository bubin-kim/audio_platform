# hooks/ — 확장 지점 (이벤트 훅)

> MVP에서는 **구독자가 없다**. "우체통만 설치하고 아무도 편지를 안 읽는" 상태(02 §7).

Service가 주요 사건이 끝날 때 여기의 훅을 발화한다. 핵심 로직(커팅·저장)은
Notion/Drive/GitHub의 존재를 **전혀 모른다**. 그래서 MCP 없이도 완전히 동작한다(P4).

## 훅 목록 (events.py)
| 훅 | 발화 시점 | V2 구독 예정 |
|---|---|---|
| `on_upload_complete` | 업로드+메타추출 완료 | Notion "데이터 추가됨" 기록 |
| `on_processing_done` | 커팅 Job 완료 | Drive 업로드 + Notion 연구일지 |
| `on_dataset_exported` | Metadata.csv 생성 | GitHub 커밋(Dataset 버전) |

## V2에서 붙이는 법
`events.py`의 각 훅에 콜백을 등록(subscribe)하면 된다. Service 코드는 손대지 않는다.
