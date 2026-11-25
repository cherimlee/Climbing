"""
암장 정보 정기 점검 (GitHub Actions: .github/workflows/check-gyms.yml)

- 매월 25일 오후: 암장 공식 웹사이트가 지난번과 달라졌는지 확인(해시 비교) + 휴무·운영시간·세팅 등 키워드 줄
- 설·추석 연휴 약 2주 전(매주 월요일에 확인): 같은 확인 + 명절 운영 확인 알림
- 12월 15일: 같은 확인 + 공휴일 목록(krHolidays) 갱신 알림

공식 웹사이트만 봅니다. 인스타그램·네이버/카카오 지도·블로그·카페는 긁지 않고, 검색 API도 쓰지 않습니다.
결과: checks/점검_YYYYMMDD_<mode>.md 를 커밋하고 GitHub 이슈로 알림.
ANTHROPIC_API_KEY가 있으면 바뀐 사이트를 Claude API로 읽어 운영시간·가격 등 고칠 내용을
DB(docs/data/climbing_gyms.json)에 적어 둠 → 워크플로가 그 변경을 PR로 올림(main에 바로 넣지 않음).
키가 없으면 DB는 그대로.
"""
import datetime as dt
import hashlib
import html
import json
import os
import re
import sys
import time
import urllib.parse
from pathlib import Path

import requests

KST = dt.timezone(dt.timedelta(hours=9))
NOW = dt.datetime.now(KST)
TODAY = NOW.date()
ROOT = Path(__file__).resolve().parent
DB = ROOT / "docs" / "data" / "climbing_gyms.json"
OUT = ROOT / "checks"
HASHES = OUT / "site_hashes.json"

# 설·추석 연휴(전날~다음날, 대체공휴일 제외). 2032년 이후는 추가 필요.
HOLIDAYS = [
    ("2027 설", "2027-02-06", "2027-02-08"), ("2027 추석", "2027-09-14", "2027-09-16"),
    ("2028 설", "2028-01-26", "2028-01-28"), ("2028 추석", "2028-10-02", "2028-10-04"),
    ("2029 설", "2029-02-12", "2029-02-14"), ("2029 추석", "2029-09-21", "2029-09-23"),
    ("2030 설", "2030-02-02", "2030-02-04"), ("2030 추석", "2030-09-11", "2030-09-13"),
    ("2031 설", "2031-01-22", "2031-01-24"), ("2031 추석", "2031-09-30", "2031-10-02"),
]
HOLIDAYS = [(n, dt.date.fromisoformat(a), dt.date.fromisoformat(b)) for n, a, b in HOLIDAYS]

# Claude가 고칠 수 있는 칸 (주소·좌표·상태(폐업 등)는 사람이 확인)
EDITABLE = ("hours", "closed", "price_day", "price_other", "rental", "setting", "phone", "status_note")
MODEL = "claude-opus-5-5"
PAGE_LIMIT = 60000  # 한 사이트에서 Claude에게 보내는 글자 수 상한

SCHEDULE_MODE = {"17 5 25 * *": "monthly", "17 5 15 12 *": "yearend", "17 5 * * 1": "holiday"}

HIT = re.compile(r"휴무|휴관|휴업|운영\s?시간|영업\s?시간|단축|임시|세팅|뉴셋|탈거|이전|폐업|폐관|오픈|가격|요금|인상|리뉴얼|연휴|명절|설날|추석|연말|신정")
SKIP_SITE = ("cafe.daum.net", "cafe.naver.com", "blog.naver.com", "m.blog.naver.com", "instagram", "facebook.com",
             "booking.naver.com", "place.naver.com", "map.naver.com", "naver.me", "pf.kakao.com", "qr.kakao.com",
             "map.kakao.com", "site.naver.com")

S = requests.Session()
S.headers["User-Agent"] = "Mozilla/5.0 (cherimlee/Climbing gym-info monthly check; +https://github.com/cherimlee/Climbing)"


def pick_mode():
    m = (os.environ.get("MODE") or "auto").strip()
    if m != "auto":
        return m, holiday_soon(0, 60)
    sch = (os.environ.get("SCHEDULE") or "").strip()
    if sch in SCHEDULE_MODE:
        m = SCHEDULE_MODE[sch]
    elif TODAY.day == 25:
        m = "monthly"
    elif TODAY.month == 12 and TODAY.day == 15:
        m = "yearend"
    else:
        m = "holiday"
    if m == "holiday":
        h = holiday_soon(8, 14)  # 연휴 시작 8~14일 전 (매주 월요일 확인 → 한 번 걸림)
        if not h or (OUT / f"명절_{h[0].replace(' ', '_')}.done").exists():
            print("명절 점검 시기가 아님 → 종료")
            sys.exit(0)
        return m, h
    # 워커 알람과 GitHub 예비 예약이 둘 다 돌 때: 최근 3일 안에 같은 점검 보고서가 있으면 건너뜀
    # (두 번째 실행은 기준값이 이미 바뀌어 '변경 0곳'으로 보고서를 덮어쓰게 됨)
    for d in range(3):
        if (OUT / f"점검_{TODAY - dt.timedelta(days=d):%Y%m%d}_{m}.md").exists():
            print("이미 점검함 → 종료")
            sys.exit(0)
    return m, holiday_soon(0, 45)


def holiday_soon(lo, hi):
    for h in HOLIDAYS:
        if lo <= (h[1] - TODAY).days <= hi:
            return h
    return None


def clean(s):
    return html.unescape(re.sub(r"<[^>]+>", "", s or "")).strip()


def site_text(url):
    try:
        r = S.get(url, timeout=20)
        if r.status_code != 200 or "html" not in r.headers.get("content-type", ""):
            return None
        r.encoding = r.apparent_encoding or r.encoding
        t = re.sub(r"(?is)<(script|style|noscript)[^>]*>.*?</\1>", " ", r.text)
        t = clean(re.sub(r"(?i)<br\s*/?>|</p>|</div>|</li>|</tr>|</h\d>", "\n", t))
        lines = [re.sub(r"\s+", " ", x).strip() for x in t.split("\n")]
        return "\n".join(x for x in lines if x)
    except Exception:  # noqa: BLE001
        return None


def propose_updates(gs, url, text):
    """바뀐 공식 웹사이트 글을 Claude에게 보여 주고, DB에서 고칠 칸을 받아 온다."""
    import anthropic

    rows = [{k: g.get(k) for k in ("id", "name", "brand", "sigungu", *EDITABLE)} for g in gs]
    cut = ' truncated="true"' if len(text) > PAGE_LIMIT else ""
    prompt = (
        "아래는 한국 클라이밍 암장 공식 웹사이트의 현재 글과, 우리 지도 DB에 저장된 이 암장(들)의 정보입니다.\n"
        "웹사이트에 지금 적힌 내용과 DB가 다른 칸만 골라 새 값을 제안하세요.\n"
        "- 웹사이트에 분명히 적힌 것만. 추측하거나 다른 지점 정보를 섞지 마세요. 확실하지 않으면 제안하지 마세요.\n"
        "- 새 값은 DB의 기존 값과 같은 말투·형식(예: '20,000원', ' / '로 구분)으로 쓰세요.\n"
        "- 임시 휴무·단축 운영 같은 일시적 공지는 status_note에 날짜와 함께 짧게 쓰세요.\n"
        "- 고칠 게 없으면 빈 목록을 돌려주세요.\n"
        f"- 고칠 수 있는 칸: {', '.join(EDITABLE)}\n\n"
        f"<db>\n{json.dumps(rows, ensure_ascii=False, indent=1)}\n</db>\n\n"
        f'<website url="{url}"{cut}>\n{text[:PAGE_LIMIT]}\n</website>'
    )
    schema = {
        "type": "object",
        "properties": {"changes": {"type": "array", "items": {
            "type": "object",
            "properties": {
                "id": {"type": "string", "enum": [g["id"] for g in gs]},
                "field": {"type": "string", "enum": list(EDITABLE)},
                "new_value": {"type": "string"},
                "evidence": {"type": "string", "description": "근거가 된 웹사이트 문장 그대로"},
            },
            "required": ["id", "field", "new_value", "evidence"],
            "additionalProperties": False,
        }}},
        "required": ["changes"],
        "additionalProperties": False,
    }
    client = anthropic.Anthropic()
    r = client.beta.messages.create(
        model=MODEL,
        max_tokens=16000,
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        output_config={"effort": "high", "format": {"type": "json_schema", "schema": schema}},
        messages=[{"role": "user", "content": prompt}],
    )
    if r.stop_reason != "end_turn":
        print("claude", url, r.stop_reason)
        return []
    out = json.loads(next(b.text for b in r.content if b.type == "text"))["changes"]
    return [c for c in out if c["new_value"].strip() and c["new_value"].strip() != str(next(g for g in gs if g["id"] == c["id"]).get(c["field"]) or "")]


def apply_updates(gyms, proposals):
    """제안을 DB에 적고, 실제로 바뀐 줄 목록을 돌려준다."""
    by_id = {g["id"]: g for g in gyms}
    done = []
    for url, changes in proposals:
        for c in changes:
            g = by_id[c["id"]]
            old = g.get(c["field"])
            g[c["field"]] = c["new_value"].strip()
            g["updated"] = TODAY.isoformat()
            if url not in (g.get("sources") or []):
                g["sources"] = (g.get("sources") or []) + [url]
            done.append((g, c, old, url))
    return done


def md_cell(s, n=120):
    s = re.sub(r"\s+", " ", str(s or "")).replace("|", "/")
    return s if len(s) <= n else s[: n - 1] + "…"


def main():
    mode, hol = pick_mode()
    print("mode", mode, hol)
    gyms = json.loads(DB.read_text(encoding="utf-8"))
    targets = [g for g in gyms if g.get("status") in ("운영중", "폐업예정")]
    OUT.mkdir(exist_ok=True)

    # 공식 웹사이트 변경
    hashes = json.loads(HASHES.read_text(encoding="utf-8")) if HASHES.exists() else {}
    first_run = not hashes
    site_rows, site_fail, checked = [], 0, 0
    texts = {}
    by_url = {}
    for g in targets:
        u = (g.get("website") or "").strip()
        if not u.startswith("http") or any(s in urllib.parse.urlparse(u).netloc.lower() for s in SKIP_SITE):
            continue
        by_url.setdefault(u, []).append(g)
    for u, gs in by_url.items():
        t = site_text(u)
        time.sleep(0.5)
        if t is None:
            site_fail += 1
            continue
        checked += 1
        h = hashlib.sha256(t.encode()).hexdigest()
        old = hashes.get(u, {})
        if old.get("hash") and old["hash"] != h:
            oldlines = set(old.get("lines", []))
            new_lines = [x for x in t.split("\n") if HIT.search(x) and x not in oldlines and len(x) < 200][:6]
            site_rows.append((gs, u, new_lines))
            texts[u] = t
        hashes[u] = {"hash": h, "at": TODAY.isoformat(), "lines": [x for x in t.split("\n") if HIT.search(x) and len(x) < 200]}
    HASHES.write_text(json.dumps(hashes, ensure_ascii=False, indent=1), encoding="utf-8")

    # 바뀐 사이트 → Claude API로 고칠 내용 뽑아 DB에 적기 (워크플로가 PR로 올림)
    done, ai_fail = [], []
    if site_rows and os.environ.get("ANTHROPIC_API_KEY"):
        proposals = []
        for gs, u, _ in site_rows:
            try:
                proposals.append((u, propose_updates(gs, u, texts[u])))
            except Exception as e:  # noqa: BLE001
                print("claude 실패", u, repr(e)[:300])
                ai_fail.append(u)
        done = apply_updates(gyms, proposals)
        if done:
            DB.write_text(json.dumps(gyms, ensure_ascii=False, indent=2), encoding="utf-8")

    # 보고서
    title_mode = {"monthly": "월간 점검", "holiday": (f"명절 점검 ({hol[0]})" if hol else "명절 점검"), "yearend": "연말연시 점검"}[mode]
    L = [f"# 암장 정보 {title_mode} — {TODAY.isoformat()}", ""]
    L.append(f"- 대상: 운영중 암장 {len(targets)}곳 중 공식 웹사이트가 있는 {len(by_url)}개 사이트")
    if hol:
        L.append(f"- 다가오는 연휴: **{hol[0]}** {hol[1]:%m/%d}~{hol[2]:%m/%d} (대체공휴일은 따로 확인)")
    L.append(f"- 공식 웹사이트 변경 **{len(site_rows)}곳** (확인 {checked}곳 · 실패 {site_fail}곳{' · 첫 실행이라 기준값만 저장' if first_run else ''})")
    after = ("Claude가 읽고 고친 내용은 아래 표와 PR에 있어요. PR을 머지해야 지도에 반영돼요." if done else
             "DB는 바뀌지 않았어요. 확인 후 Claude에게 \"이 이슈 반영해줘\"라고 하면 됩니다.")
    L += ["", f"> 웹사이트 내용이 바뀐 **후보**입니다. 인스타 공지는 확인하지 않으니, 명절·연말엔 즐겨 가는 암장 공지를 직접 한 번 보세요. {after}", ""]
    if mode == "holiday" and hol:
        L += [f"- [ ] 즐겨 가는 암장 인스타에서 {hol[0]} 연휴 운영 공지 확인", "- [ ] 대체공휴일이 있는지, 지도 `krHolidays()`에 들어 있는지 확인", ""]
    if mode == "yearend":
        L += [f"- [ ] 지도 `map.html`의 `krHolidays()`에 {TODAY.year + 1}년 공휴일이 다 들어 있는지 확인", f"- [ ] `check_gyms.py`의 `HOLIDAYS` 목록 끝이 {HOLIDAYS[-1][0]} → 부족하면 추가", ""]

    if site_rows:
        L += ["## 공식 웹사이트가 바뀐 곳", ""]
        for gs, u, lines in site_rows:
            L.append(f"- **{', '.join(g['name'] for g in gs[:4])}{' 외' if len(gs) > 4 else ''}** — {u}")
            for x in lines:
                L.append(f"  - {md_cell(x, 160)}")
        L.append("")
    if not site_rows:
        L += ["바뀐 웹사이트가 없어요.", ""]
    U = []
    if done:
        U += ["## Claude가 고친 내용 (PR로 올림, 머지해야 지도에 반영)", "", "| 암장 | 칸 | 전 | 후 | 근거 |", "|---|---|---|---|---|"]
        for g, c, old, url in done:
            U.append(f"| {md_cell(g['name'], 30)} | {c['field']} | {md_cell(old, 80)} | {md_cell(c['new_value'], 80)} | {md_cell(c['evidence'], 100)} ([출처]({url})) |")
        U.append("")
    elif site_rows and os.environ.get("ANTHROPIC_API_KEY"):
        L += ["Claude가 바뀐 사이트를 읽어 봤지만 지도 데이터에서 고칠 칸은 찾지 못했어요.", ""]
    if ai_fail:
        U += [f"Claude가 읽지 못한 사이트 {len(ai_fail)}곳: " + ", ".join(ai_fail), ""]
    L += U
    body = "\n".join(L)
    upd = os.environ.get("UPDATE_BODY")
    if upd and done:
        Path(upd).write_text(f"# 암장 정보 자동 업데이트 — {TODAY.isoformat()}\n\n" + "\n".join(U) + "\n머지하면 지도 데이터가 자동으로 다시 만들어져요.\n", encoding="utf-8")
    rpt = OUT / f"점검_{TODAY:%Y%m%d}_{mode}.md"
    rpt.write_text(body, encoding="utf-8")
    if mode == "holiday" and hol:
        (OUT / f"명절_{hol[0].replace(' ', '_')}.done").write_text(TODAY.isoformat(), encoding="utf-8")
    print(body[:3000])

    # GitHub 이슈로 알림
    tok, repo = os.environ.get("GITHUB_TOKEN"), os.environ.get("GITHUB_REPOSITORY")
    if tok and repo:
        n = len(site_rows)
        link = f"https://github.com/{repo}/blob/main/climbing-report/checks/{urllib.parse.quote(rpt.name)}"
        issue_body = body if len(body) < 60000 else body[:60000] + f"\n\n…(잘림) 전체: {link}"
        r = S.post(f"https://api.github.com/repos/{repo}/issues", headers={"Authorization": f"Bearer {tok}", "Accept": "application/vnd.github+json"},
                   json={"title": f"[{title_mode}] {TODAY:%Y-%m-%d} 웹사이트 변경 {n}곳", "body": issue_body + f"\n\n보고서 파일: {link}"}, timeout=20)
        print("issue", r.status_code, r.json().get("html_url") if r.ok else r.text[:300])
        if r.ok and os.environ.get("GITHUB_OUTPUT"):
            with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as f:
                f.write(f"issue={r.json()['number']}\n")


if __name__ == "__main__":
    main()
