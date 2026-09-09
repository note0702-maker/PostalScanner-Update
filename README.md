# PostalScanner Update

PostalScanner Windows 자동업데이트 저장소입니다.

- `source/PostalScanner.py.gz.b64.part00` ~ `part04`를 GitHub Actions가 합쳐 원본 `PostalScanner.py`를 복원합니다.
- 복원된 소스의 `APP_VERSION`을 읽어 Windows용 `PostalScanner.exe`와 `PostalScanner_Updater.exe`를 자동 빌드합니다.
- Release ZIP과 SHA-256을 자동 생성합니다.
- `update_manifest.json`을 자동 갱신합니다.
- 설치된 PostalScanner는 실행 시 manifest를 확인하고, 새 버전이 있으면 사용자 승인 후 자동 설치·재실행합니다.

개인정보, API Key, 실제 업무 Excel, output/audit 파일은 이 저장소에 올리지 않습니다.
