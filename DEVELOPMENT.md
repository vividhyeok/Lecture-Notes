# Lecture Notes v0.2.0 개발 구조

## 주요 구성

- `extension/`: Chrome에서 로드하는 Manifest V3 확장. 사이드 패널 UI, LMS 문맥 수집, DownloadHelper 다운로드 감지를 담당.
- `extension/worker.js`: 다운로드가 실제 지원 강의 문맥에서 시작됐는지 검증한 뒤 백엔드에 가져오기 요청. 성공한 파일은 같은 문맥으로 자동 binding을 시도.
- `extension/navigation.js`: 강의 탐색, 아이콘 도구, 보관함, 처리 파이프라인 표시, AI 품질 프리셋 등 편의 UI.
- `backend/core.py`: 안전한 파일 처리, 자막 파싱, 입력 분할, Windows DPAPI.
- `backend/provider.py`: OpenAI 음성 전사/Responses API 클라이언트와 노트·시험 자료 프롬프트.
- `backend/library.py`: SQLite 색인/작업 큐, 파일 중복 방지, 전사 캐시, 기본 노트·시험 처리, Obsidian 내보내기.
- `backend/convenience.py`: v0.2.0 정책 계층. 외부 다운로드 폴더 event-only 기본값, 보관함, 품질 프리셋, 긴 노트 2-pass, 시험 자료 map/reduce를 적용.
- `backend/vault_sync.py`: Obsidian Markdown과 portable binding record 동기화.
- `backend/server.py`: `127.0.0.1` 전용 인증 HTTP API.
- `backend/app.py`: 실제 실행 entry point. ConvenienceLibrary와 v0.2.0 health handler를 주입.
- `setup.ps1`: 초기화, Windows 로그인 자동 시작 등록, 시작 메뉴 바로가기 생성.
- `update.ps1`: 실행 중인 구버전 서버 종료 → setup 재적용 → 새 서버 시작 → Chrome 확장 관리 화면 열기.
- `build_release.py`: 사용자 데이터 없는 설치/업데이트 ZIP 생성.

## 사용자 데이터

아래 경로는 Git과 배포 ZIP에 포함하지 않는다.

- `library/`: 원본 강의와 내부 처리 결과
- `Obsidian/`: 기본 Markdown 보관함
- `.local/`: 연결 토큰, DPAPI로 보호된 API 키, SQLite 색인, 로그
- `node_modules/`

배포 ZIP은 프로그램 파일만 포함하므로 기존 설치 폴더에 덮어써도 사용자 자료를 교체하지 않는다.

## 가져오기 정책

기본 정책은 **명시적 강의 문맥 우선**이다.

- `library/inbox`: 사용자가 앱에 주는 명시적 입력이므로 항상 자동 스캔.
- 외부 `watch_folder`: 기본적으로 전체 스캔하지 않음.
- Chrome DownloadHelper 감지: 지원 LMS/YouTube 강의 문맥이 존재하고 지원 파일 형식일 때만 `/api/download-complete` 호출.
- YouTube: 음악 유입을 막기 위해 별도 opt-in.
- 사용자가 `watch_all_files`를 켠 경우에만 외부 폴더 전체 스캔.

자동 다운로드 가져오기 성공 후 같은 context로 `bind_lecture`를 수행한다. binding 실패는 성공한 파일 import를 롤백하지 않으며 UI의 수동 연결이 recovery path다.

## 보관 정책

보관은 삭제가 아니다. `archived_lectures`는 로컬 설정에 ID 목록으로 저장되고 UI의 활성/보관 뷰만 필터한다.

동기화와 binding 중복 제거 같은 내부 유지 작업은 보관 여부와 무관하게 전체 강의를 본다. 이렇게 해야 숨겨진 강의가 같은 LMS pageKey를 계속 점유하거나 maintenance에서 빠지는 문제를 피할 수 있다.

## AI 처리

품질 프리셋:

- `fast` → `gpt-5.6-luna`
- `balanced` → `gpt-5.6-terra`
- `precise` → `gpt-5.6-sol`
- `custom` → 직접 지정한 `text_model`

기존 기본값 `gpt-4.1-mini`는 `balanced`로 마이그레이션한다.

### 긴 강의노트

1. `split_text()`로 안전하게 분할.
2. 최대 3구간 병렬 note generation.
3. `finalize_long_notes`가 켜져 있고 구간이 2개 이상이면 전체 결과를 다시 읽어 제목 중복, 용어, 계층만 통합.
4. 원문 사실·코드·수식·예시 삭제나 외부 지식 추가는 finalization prompt에서 금지.

### 시험 자료

1. 저장된 노트/전사본만 수집; 음성 재전사 없음.
2. 긴 입력은 구간별 `EXAM_PROMPT` map.
3. map 산출물은 `범위별정리-NNN.md`로 보존.
4. 전체 map 결과를 `EXAM_MERGE_PROMPT`로 reduce.
5. reduce 호출 실패 시 map 결과 전체를 최종 문서에 fallback하여 자료 손실 방지.

## 보안/무결성 원칙

- 모든 `/api`는 임의 연결 토큰 요구. `/health` 외에는 인증 필수.
- Host/Origin 검사 및 loopback bind.
- 임의 filesystem path가 API에서 통과하지 못하도록 `inside()` 사용.
- API 키나 제공자 오류 본문을 로그/브라우저에 그대로 노출하지 않음.
- Markdown raw HTML 실행 금지.
- 노트 저장 직전 optimistic conflict check로 Obsidian의 최신 변경 덮어쓰기 방지.
- 기존 노트 재정리 시 versions 백업 및 생성 중 수정 감지.
- 작업 실패는 무한 자동 재시도하지 않음.

## 로컬 검증

```text
npm ci
python backend/app.py --init-only
npm run check
python tests/test_backend.py
python tests/test_convenience.py
npm run test:browser
python build_release.py
```

`npm run test:browser`는 실제 `backend/app.py`를 띄워 Chrome headless에서 import, Markdown 안전 렌더링, 검색, 편집 충돌, 보관/복원, 강의 binding, 작은 화면, A4 PDF를 검증한다.

GitHub Actions는 `windows-latest`에서 동일 검증을 수행한 뒤 `Lecture-Notes-v0.2.0.zip`을 artifact로 생성한다.
