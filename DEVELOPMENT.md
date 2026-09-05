# 파일 구성

- extension/: Chrome에서 선택할 폴더. panel.html은 로컬 서버의 설정·자료함 화면으로도 재사용.
- backend/core.py: 안전한 파일 처리, 자막 파싱, 손실 없는 입력 분할, Windows DPAPI.
- backend/provider.py: OpenAI 음성 전사/Responses API, 사용자 노트 프롬프트.
- backend/library.py: SQLite 작업 대기열, 중복 방지, 구간 캐시, 폴더 감시, Obsidian 내보내기.
- backend/server.py: 127.0.0.1 전용 인증 HTTP API와 업로드.
- library/: 사용자 자료 및 원본. Git/배포 제외.
- Obsidian/: 기본 사용자 보관함. Git/배포 제외.
- .local/: 연결 키, 암호화 API 키, SQLite 색인. Git/배포 제외.

보안: 모든 /api 경로에 임의 연결 키 요구, Host/Origin 검사, cross-site 설정 스크립트 로드 차단, 파일 접근 경로 제한. Markdown의 raw HTML은 실행되지 않음. HTTP 요청 로그에 API 키나 본문을 기록하지 않음.

메모: 서버는 한 인스턴스로 실행. 작업이 완료한 구간은 캐시하고 재개. 알 수 없는 provider/로컬 예외 본문은 사용자에 그대로 반환하지 않음. API 실패는 자동 무한 재시도하지 않으며 작업 UI에서 재시도. 노트 생성은 기존 노트를 덮어쓰지 않음. 분류 변경은 원래 파일 보존.
