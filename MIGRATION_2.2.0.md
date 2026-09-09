# PostalScanner 2.2.0 개발 전환 메모

## 목적
2.1.x에서 누적된 PaddleOCR/CLOVA 실행 경로를 제거하고, 기존 업무 판독 규칙을 별도 모듈로 보존한 OpenAI-only 구조로 정리한다.

## 안정판 보호
- 이 작업은 `dev/2.2.0-openai-cleanup` 브랜치에서만 진행한다.
- 안정 `main` 브랜치의 2.1.5 manifest는 변경하지 않는다.
- 개발 빌드는 GitHub Release를 만들지 않고 Actions artifact만 생성한다.
- Windows 실기 테스트 완료 전 자동업데이트 배포를 금지한다.

## 데이터 구조
2.2.0부터 업무데이터/설정은 프로그램 파일과 분리한다.

```text
PostalScanner/
├─ PostalScanner.exe
├─ _internal/
├─ updater/
│  └─ PostalScanner_Updater.exe
├─ resources/
│  └─ 요금후납_우편물_발송표_자동입력용.xlsx
└─ data/
   ├─ original/
   ├─ output/
   ├─ audit/
   ├─ openai_key.dat
   ├─ openai_config.json
   └─ address_aliases.json
```

2.1.x 루트에 존재하는 `original`, `output`, `audit`, `metrics`, `openai_key.dat`, `openai_config.json`, `address_aliases.json`은 시작 시 `data/`로 1회 이전한다.

## 보존한 일반우편 규칙
- 받는 사람의 주소/이름만 추출
- 발신인/회신주소/우편번호/바코드/등기번호/요금후납/로고/광고문구 제외
- 도/광역시가 생략된 `포항시 남구 ...` 형태 주소 인정
- 여러 줄 주소와 건물/동/호/층 등 상세주소 결합
- `담당자` 수취인 후보 인정
- 이름의 `귀하/님/선생님` 제거
- 영문은 K/T만 허용, `KT` 유지
- 보이지 않는 내용 추측 금지

## 보존한 인감대장 규칙
- 가장 아래 실제 작성행만 판독
- 가로선/세로선/행번호를 작성행 판정 기준으로 사용하지 않음
- 손글씨와 인쇄된 `시/구/도/군/장`을 결합
- 가까운 인쇄 접미사가 OCR 손글씨보다 우선할 수 있음
- 등기번호 열의 손글씨 한글을 수신인 이름으로 사용
- 인쇄된 양식 문구와 단독 `시/구/도/군/장` 제외
- `시시/구구/군군/구시군` 같은 깨진 행정단위 방지
- 문맥상 `육장/욕장/읖장/읏장`을 `읍장`으로 보정
- 보이지 않는 내용 추측 금지

## 업데이트 안전 원칙
1. 새 ZIP 전체 다운로드
2. SHA-256 검증
3. 별도 staging 경로에 압축 해제
4. 새 `PostalScanner.exe` 및 `_internal` 존재 확인
5. 기존 PostalScanner PID 종료 확인
6. 기존 설치 폴더를 통째로 백업 rename
7. 검증된 staging 폴더를 새 설치 폴더로 rename
8. 사용자 데이터 복원/보존
9. 새 앱 실행 확인
10. 새 앱 시작 실패 시 기존 설치 자동 rollback

기존 설치를 먼저 삭제하는 방식은 사용하지 않는다.

## 안정판 승격 전 Windows 필수 테스트
1. 일반 우편물 실제 샘플 10건 이상
2. 인감대장 실제 샘플 10건 이상
3. Excel 저장 + F:I 병합셀 포함 마지막 입력 취소
4. DPAPI API Key 저장 후 앱 재시작
5. `data/original` 삭제 후 원본 Excel 자동 복원
6. 정상 업데이트 성공 경로
7. 잘못된 SHA / 새 EXE 누락 패키지에서 기존 프로그램 무변경 확인
8. 새 앱 시작 실패 시 이전 버전 자동 rollback 확인

## 2.1.5 → 2.2.0 자동업데이트 주의
첫 전환을 실행하는 updater는 2.1.5에 설치된 구형 updater다. 따라서 2.2.0 자체의 안전 updater가 완성되어도 2.1.5에서 곧바로 안정 manifest를 2.2.0으로 올리면 안 된다.

첫 전환용 bridge 또는 수동 개발 빌드 검증이 완료된 뒤 안정 업데이트 경로를 별도로 설계한다.
