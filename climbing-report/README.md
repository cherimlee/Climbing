# climbing-report — 소모임 클라이밍 정모 자동 수집

매일 GitHub 서버가 소모임 공개 페이지에서 서울·경기 클라이밍 크루(멤버 30명 이상)의 **오늘 정모**를 모아
암장별 정모 수·참석 인원·낮클/퇴근클을 집계하고, GitHub Pages로 공개합니다.

- 낮클(day): 시작 시각 **~16:59** / 퇴근클(eve): **17:00~**
- 참석 인원: 정모 카드에 표시된 집계 숫자만 사용 (멤버 이름 등 개인정보는 읽지도 저장하지도 않음)
- `gym_id`는 `climbing_gyms.json`·`climbing-map.html`의 암장 id와 같습니다.

## 파일 구성

| 파일 | 역할 |
|---|---|
| `collect.py` | 수집·매칭·집계 스크립트 |
| `crews.json` | 수집 대상 크루 목록 (크루 추가/삭제는 여기서) |
| `gyms.json` | 암장 id·이름·좌표 (climbing_gyms.json에서 추출) |
| `collect.yml` | 매일 09:30·17:30 KST에 깨어나 09:56·17:56에 수집(10시·18시 직전 값) — **GitHub에서 `.github/workflows/collect.yml` 위치에 만들어야 함** (3번 참고) |
| `docs/data/Somoim_MMDD.json` | 날짜별 결과 (같은 날 2회 실행 시 병합) |
| `docs/data/latest.json` | 가장 최근 결과 — 지도에서 불러올 주소 |

## 설정 순서 (처음 한 번, 약 15분)

1. **GitHub 계정 만들기** — https://github.com (이미 있으면 생략)
2. **저장소 만들기** — 오른쪽 위 `+` → *New repository* → 이름 `climbing-report` → **Public** 선택 → *Create repository*
   - 무료 계정에서 GitHub Pages를 쓰려면 Public이어야 합니다. 저장소 내용(크루 이름, 정모 제목·장소)이 공개된다는 점을 감안하세요.
3. **파일 올리기** — 저장소 첫 화면의 *uploading an existing file* 링크 → 이 폴더의 파일을 **폴더 구조 그대로** 끌어다 놓기 → *Commit changes*
   - 단, `collect.yml`은 올리지 말고 따로 만듭니다: *Add file → Create new file* → 파일 이름 칸에 `.github/workflows/collect.yml` 입력(슬래시를 치면 폴더가 자동 생성) → 이 폴더의 `collect.yml` 내용을 메모장으로 열어 복사·붙여넣기 → *Commit changes*
   - Git을 쓸 줄 알면: `git init` → `git add .` → `git commit -m init` → `git remote add origin https://github.com/<아이디>/climbing-report.git` → `git push -u origin main`
4. **쓰기 권한 허용** — 저장소 *Settings → Actions → General → Workflow permissions* → **Read and write permissions** → *Save*
5. **첫 실행 테스트** — *Actions* 탭 → (처음이면 *I understand… enable* 클릭) → `collect-somoim` → **Run workflow**. 2~3분 뒤 초록 체크가 뜨고 `docs/data/`에 파일이 생기면 성공
6. **GitHub Pages 켜기** — *Settings → Pages* → Source: **Deploy from a branch** → Branch: `main`, 폴더: **/docs** → *Save*
   - 1~2분 뒤 `https://<아이디>.github.io/climbing-report/map.html` 에서 지도, `…/data/latest.json` 에서 데이터 확인

## climbing-map에 연결하기

지도 페이지에서 `https://<아이디>.github.io/climbing-report/data/latest.json` 을 불러와 `gyms[].gym_id`로 암장과 합치면 됩니다.
(지도는 Claude에게 "latest.json을 읽어 정모 레이어를 추가해줘"라고 요청하면 붙여 드릴 수 있습니다.)

## 운영 팁

- **실행 시각 바꾸기**: `collect.yml`의 `cron`은 **UTC**입니다. KST = UTC+9. 예) 08:50 KST → `50 23 * * *`(전날 UTC)
- **수집 타이밍**: GitHub 예약은 늦게 시작하는 일이 잦아 30분 일찍(09:30, 17:30) 깨운 뒤, `collect.py`가 09:56·17:56까지 기다렸다가 4개씩 동시에 받아 약 30~40초 안에 끝냅니다. GitHub이 그보다 늦게 깨우면 기다리지 않고 바로 수집합니다. 시각을 바꾸려면 `START_AT`(예: `09:50`)을 지정하세요.
- **이미 시작한 정모**는 카드에서 참석 인원이 사라집니다. 같은 날 오후 실행에서는 아침 값이 유지됩니다(17시대 정모 등).
- **수동 실행**: Actions 탭 → Run workflow → `start_at`을 `now`로 두면 기다리지 않고 바로 수집합니다.
- **60일 규칙**: Public 저장소는 60일 동안 저장소 활동이 없으면 예약 실행이 자동 중지됩니다. 이 워크플로는 매일 결과를 커밋하므로 보통 문제없지만, 멈추면 Actions 탭에서 다시 *Enable* 하세요.
- **실패 알림**: 크루 절반 이상 수집에 실패하면(차단·페이지 구조 변경 의심) 실행이 빨간색으로 끝나고 GitHub이 메일로 알려줍니다.
- **장소 매칭 추가**: 새 암장 별칭이 보이면 `collect.py`의 `ALIASES`에 `(정규식, "암장ID")` 한 줄을 추가합니다. `place_type`이 `미상`인 정모를 가끔 확인하세요.
- **예의**: 요청 사이 1초 간격(`REQUEST_DELAY`)을 두었습니다. 크루 수를 크게 늘리면 이 값을 줄이지 마세요.
