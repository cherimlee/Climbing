"""소모임 클라이밍 크루 정모 수집기 (GitHub Actions에서 매일 실행)

- 대상: crews.json (서울·경기 멤버 30명 이상 클라이밍 크루)
- 수집: 각 크루 공개 페이지의 '정모 일정' 카드 → 오늘(KST) 정모의 시간·장소·참석/정원
- 개인정보: 멤버·운영진 영역은 잘라내고 읽지 않음. 참석은 카드의 집계 숫자만 사용
- 낮클/퇴근클: 시작 시각 ~16:59 = day, 17:00~ = eve
- 출력: docs/data/Somoim_MMDD.json (같은 날 여러 번 실행하면 병합), docs/data/latest.json, docs/index.html
- 실행 타이밍: GitHub 예약은 늦게 시작할 수 있어 9:30/17:30에 깨운 뒤, 9:56/17:56까지 기다렸다가 수집
  (10시·18시 정모가 시작되기 직전의 참석 인원을 잡기 위함). 늦게 깨어났으면 기다리지 않고 바로 수집.
"""
import concurrent.futures, datetime, html, json, os, re, sys, threading, time
import requests

KST = datetime.timezone(datetime.timedelta(hours=9))
BASE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(BASE, "docs", "data")
DELAY = float(os.environ.get("REQUEST_DELAY", "1.0"))  # 워커별 요청 간격(초) — 소모임 서버 부담 완화
WORKERS = int(os.environ.get("WORKERS", "4"))           # 동시 요청 수. 4 × 1초 간격 ≈ 85곳 25~40초
START_AT = os.environ.get("START_AT", "auto")           # "auto" | "HH:MM" | "now"


def wait_until_start():
    """오전 실행이면 09:56, 오후 실행이면 17:56(KST)까지 대기. 이미 지났으면 즉시 시작."""
    now = datetime.datetime.now(KST)
    if START_AT == "now":
        return
    if START_AT == "auto":
        hh, mm = (9, 56) if now.hour < 13 else (17, 56)
    else:
        hh, mm = map(int, START_AT.split(":"))
    target = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
    wait = (target - now).total_seconds()
    if 0 < wait <= 45 * 60:
        print(f"waiting {int(wait)}s until {target:%H:%M} KST", flush=True)
        time.sleep(wait)
    elif wait <= 0:
        print(f"started late ({now:%H:%M} KST) — collecting immediately", flush=True)


wait_until_start()
NOW = datetime.datetime.now(KST)
TODAY = int(os.environ.get("TARGET_DATE") or NOW.strftime("%Y%m%d"))

CREWS = json.load(open(os.path.join(BASE, "crews.json"), encoding="utf-8"))
G = {g["id"]: g for g in json.load(open(os.path.join(BASE, "gyms.json"), encoding="utf-8"))}

# ── 장소명 → 암장 ID (순서 중요: 위에서부터 먼저 맞는 것 사용) ──────────────────
ALIASES = [
    (r"2\s?years|2년집|염창|투이얼즈", "SEL-040"),
    (r"(구로|구숲).*(서울숲|숲)|서울숲.*구로|서울🌲.*구로|^구숲$", "SEL-053"),
    (r"잠실.*(서울숲|숲)|서울숲.*잠실", "SEL-116"),
    (r"영등숲|영숲|영등포.*(서울숲|숲)|서울숲.*영등포", "SEL-128"),
    (r"종숲|종로.*(서울숲|숲)|서울숲.*종로|설숲", "SEL-140"),
    (r"영등포.*경기장|영등포클라이밍경기장", "SEL-131"),
    (r"알레.*영등포", "SEL-130"), (r"알레.*혜화", "SEL-141"), (r"알레.*강동|강동.*알레", "SEL-019"),
    (r"을지로.*손상원|손상원.*을지|을손상", "SEL-146"),
    (r"판교", "GGI-058"),
    (r"강남.*손상원|손상원.*강남|강손|강상원", "SEL-098"),
    (r"을지로\s?담장|담장.*을지로", "SEL-147"), (r"신촌\s?담장|담장.*신촌", "SEL-094"),
    (r"피커스.*신촌", "SEL-095"), (r"피커스.*구로", "SEL-056"), (r"종로\s?피커스|피커스.*종로", "SEL-143"),
    (r"강클팍|(클라이밍파크|클팍).*강남", "SEL-005"), (r"클라이밍파크.*신논현|신논현", "SEL-006"),
    (r"종로\s?클라이밍파크|(클라이밍파크|클팍).*종로", "SEL-142"),
    (r"더클.*일산|일산.*더클", "GGI-012"),
    (r"(더\s?클|더클라임).*이수|이수.*더클", "SEL-078"), (r"(더\s?클|더클라임).*양재|양재.*더클", "SEL-004"),
    (r"(더\s?클|더클라임).*신림|신림.*더클", "SEL-043"), (r"(더\s?클|더클라임).*문래|문래.*더클", "SEL-125"),
    (r"(더\s?클|더클라임).*연남|연남.*더클", "SEL-083"), (r"(더\s?클|더클라임).*논현", "SEL-097"),
    (r"(더\s?클|더클라임).*사당", "SEL-042"), (r"(더\s?클|더클라임).*성수", "SEL-105"),
    (r"(더\s?클|더클라임).*마곡", "SEL-036"), (r"(더\s?클|더클라임).*강남|강남\s?더클", "SEL-003"),
    (r"온플릭", "SEL-021"), (r"닷\s?클라이밍", "SEL-112"), (r"스톤즈", "SEL-044"), (r"크래커", "SEL-152"),
    (r"오프더월", "SEL-136"), (r"서울볼더스.*목동", "SEL-123"), (r"훅클라이밍.*왕십리", "SEL-108"),
    (r"캐치스톤", "GGI-052"), (r"스파이시", "GGI-033"), (r"더렛지", "GGI-106"), (r"픽\s?클라이밍", "GGI-039"),
    (r"퍼즐", "GGI-045"), (r"킨디", "GGI-070"), (r"피크닉", "GGI-087"), (r"슈퍼비", "GGI-075"),
    (r"볼더메이트.*기흥", "GGI-125"), (r"락페이스", "GGI-063"), (r"클라임어클락", "GGI-170"), (r"페퍼", "GGI-006"),
    (r"어스|모란", "GGI-065"), (r"광명.*인공암벽", "GGI-021"), (r"새물공원", "GGI-113"),
]
UNLISTED = {r"비블럭": "비블럭", r"허브클라이밍": "허브클라이밍", r"딥스테이션": "딥스테이션(용인)",
            r"미스터리딤": "미스터리딤(일산)", r"어웨이크": "어웨이크(대전)", r"킨디.*수원역": "킨디클라이밍 수원역점"}
OUTDOOR = r"장거리 원정|자연|바위|암$|죽도|조비산|할매|크롱|여장군|구성 일대|모락산|파빌리온|예술공원|잠수함|강화수련장|아쿠아라인|평화의공원"
NONGYM = r"바베큐|펜션|루프탑|MT|엠티|방탈출|전용 앱"


def match(place, title):
    for txt in ((place or "").strip(), title or ""):
        if not txt or txt == "-":
            continue
        if re.search(NONGYM, txt):
            return "기타", None, None
        for k, v in UNLISTED.items():
            if re.search(k, txt):
                return "목록외암장", None, v
        for rx, gid in ALIASES:
            if re.search(rx, txt, re.I):
                return "암장", gid, G[gid]["name"]
        if re.search(OUTDOOR, txt):
            return "자연암장", None, None
    return "미상", None, None


def parse_crew_page(h):
    """그룹 객체의 정모 필드(최대 4건) + 정모 카드의 참석/정원 숫자. 멤버 영역은 읽지 않는다."""
    ch = re.findall(r'self.__next_f.push\(\[1,"(.*?)"\]\)</script>', h, re.S)
    s = "".join(json.loads('"' + x + '"') for x in ch)
    i = s.find('"group":{')
    g = json.JSONDecoder().raw_decode(s[i + 8:])[0] if i >= 0 else {}
    evs = []
    for suf in ("", "2", "3", "4"):
        if g.get("e_d" + suf):
            evs.append({"title": html.unescape((g.get("en" + suf) or "").strip()), "date": g.get("e_d" + suf),
                        "time": g.get("e_t" + suf) or 0, "place": g.get("el" + suf), "capacity": g.get("emm" + suf),
                        "joined": None})
    body = re.sub(r"<script.*?</script>", "", h, flags=re.S)
    txt = re.sub(r"\n\s*\n+", "\n", re.sub(r"<[^>]+>", "\n", body))
    a = txt.find("정모 일정")
    if a < 0:
        return evs
    ends = [k for k in (txt.find("운영진", a), txt.find("모임 멤버", a)) if k > a]
    seg = txt[a:min(ends) if ends else a + 3000]          # ← 정모 카드 구간만
    parts = re.split(r"\n(\d+)\s*\n/\s*\n(\d+)\s*\n", seg)
    cards = []
    for k in range(0, len(parts) - 2, 3):
        L = [x.strip() for x in parts[k].split("\n") if x.strip()]
        j = next((q for q in range(3, len(L)) if L[q] == L[q - 3] + " " + L[q - 2]), None)
        if j is not None:
            cards.append([html.unescape(L[j - 1]), int(parts[k + 1]), int(parts[k + 2]), False])
    for e in evs:
        for cd in cards:
            if not cd[3] and cd[0] == e["title"] and (e["capacity"] is None or cd[2] == e["capacity"]):
                e["joined"], cd[3] = cd[1], True
                break
    return evs


def collect():
    S = requests.Session()
    S.headers["User-Agent"] = "Mozilla/5.0 (climbing-report personal research)"
    lock = threading.Lock()
    events, errors = [], [0]

    def one(c):
        try:
            r = S.get(c["url"], timeout=30)
            r.raise_for_status()
            evs = parse_crew_page(r.text)
            seen = datetime.datetime.now(KST).strftime("%H:%M:%S")
        except Exception as ex:  # 한 크루 실패해도 계속
            with lock:
                errors[0] += 1
            print("WARN", c["name"], ex, file=sys.stderr)
            time.sleep(DELAY)
            return
        rows = []
        for e in evs:
            if e["date"] != TODAY:
                continue
            kind, gid, gname = match(e["place"], e["title"])
            t = e["time"]
            rows.append({"key": f'{c["crew_id"]}|{t}|{e["title"]}', "crew_id": c["crew_id"], "crew": c["name"],
                         "crew_url": c["url"], "time": f"{t // 100:02d}:{t % 100:02d}",
                         "slot": "day" if t < 1700 else "eve", "title": e["title"], "place_raw": e["place"],
                         "joined": e["joined"], "capacity": e["capacity"], "place_type": kind,
                         "gym_id": gid, "gym_name": gname, "seen_at": seen})
        with lock:
            events.extend(rows)
        time.sleep(DELAY)

    t0 = time.time()
    with concurrent.futures.ThreadPoolExecutor(max_workers=WORKERS) as ex:
        list(ex.map(one, CREWS))
    print(f"fetched {len(CREWS)} crews in {time.time() - t0:.0f}s with {WORKERS} workers", flush=True)
    return events, errors[0]


def merge(path, new):
    """같은 날 여러 번 실행: 이전 결과 유지 + 참석 수는 최신 값으로 갱신(끝난 정모는 페이지에서 사라지므로)."""
    old = {}
    if os.path.exists(path):
           old = {e["key"]: e for e in json.load(open(path, encoding="utf-8")).get("events", []) if "key" in e}
    for e in new:
        prev = old.get(e["key"])
        if prev and e["joined"] is None:
            e["joined"] = prev.get("joined")
        old[e["key"]] = e
    return sorted(old.values(), key=lambda x: x["time"])


def aggregate(events):
    gyms = {}
    for e in events:
        if not e["gym_id"]:
            continue
        g = G[e["gym_id"]]
        r = gyms.setdefault(g["id"], {"gym_id": g["id"], "name": g["name"], "sido": g["sido"], "sigungu": g["sigungu"],
                                     "lat": g["lat"], "lng": g["lng"],
                                     "day": {"events": 0, "joined": 0, "joined_unknown": 0},
                                     "eve": {"events": 0, "joined": 0, "joined_unknown": 0}, "crews": []})
        s = r[e["slot"]]
        s["events"] += 1
        if e["joined"] is None:
            s["joined_unknown"] += 1
        else:
            s["joined"] += e["joined"]
        if e["crew"] not in r["crews"]:
            r["crews"].append(e["crew"])
    out = list(gyms.values())
    for r in out:
        r["total"] = {"events": r["day"]["events"] + r["eve"]["events"], "joined": r["day"]["joined"] + r["eve"]["joined"]}
        r["mix"] = r["day"]["events"] > 0 and r["eve"]["events"] > 0
    return sorted(out, key=lambda r: (-r["total"]["joined"], -r["total"]["events"]))


def render_html(doc):
    m, rows = doc["meta"], []
    for r in doc["gyms"]:
        rows.append(f'<tr><td>{html.escape(r["name"])}</td><td>{r["day"]["events"]}건 · {r["day"]["joined"]}명</td>'
                    f'<td>{r["eve"]["events"]}건 · {r["eve"]["joined"]}명</td></tr>')
    return f"""<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>클라이밍 정모 리포트</title><style>
:root{{--bg:#f6f7f9;--card:#fff;--fg:#1c1e21;--muted:#6b7280;--line:#e5e7eb}}
@media(prefers-color-scheme:dark){{:root{{--bg:#0f1115;--card:#171a21;--fg:#e5e7eb;--muted:#9ca3af;--line:#2a2f3a}}}}
body{{margin:0;background:var(--bg);color:var(--fg);font:15px/1.5 system-ui,"Malgun Gothic",sans-serif}}
main{{max-width:720px;margin:0 auto;padding:16px}}table{{width:100%;border-collapse:collapse;background:var(--card)}}
td,th{{padding:8px;border-bottom:1px solid var(--line);text-align:left}}small{{color:var(--muted)}}</style></head>
<body><main><h1>🧗 클라이밍 정모 리포트</h1>
<small>{m["date"]} · 수집 {m["collected_at"]} · 소모임 · 30명 이상 크루 {m["crews"]}곳 · 낮클 ~16:59 / 퇴근클 17:00~</small>
<p>정모 {m["summary"]["events_at_gyms"]}건 · 암장 {m["summary"]["gyms"]}곳 · 참석 {m["summary"]["joined_total"]}명</p>
<table><tr><th>암장</th><th>☀️ 낮클</th><th>🌙 퇴근클</th></tr>{''.join(rows)}</table>
<p><small>데이터: <a href="data/latest.json">latest.json</a></small></p></main></body></html>"""


def main():
    os.makedirs(OUT, exist_ok=True)
    d = str(TODAY)
    path = os.path.join(OUT, f"Somoim_{d[4:]}.json")
    new, errors = collect()
    events = merge(path, new)
    gyms = aggregate(events)
    doc = {"meta": {"date": f"{d[:4]}-{d[4:6]}-{d[6:]}", "collected_at": NOW.isoformat(timespec="minutes"),
                    "crews": len(CREWS), "errors": errors,
                    "slot_rule": "day = 시작 ~16:59, eve = 17:00~",
                    "joined": "정모 카드의 참석 인원(집계 숫자). 이름 등 개인정보 미수집",
                    "summary": {"events_total": len(events), "events_at_gyms": sum(r["total"]["events"] for r in gyms),
                                "gyms": len(gyms), "joined_total": sum(r["total"]["joined"] for r in gyms)}},
           "gyms": gyms, "events": events}
    for p in (path, os.path.join(OUT, "latest.json")):
        json.dump(doc, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    open(os.path.join(BASE, "docs", "index.html"), "w", encoding="utf-8").write(render_html(doc))
    print(json.dumps(doc["meta"]["summary"], ensure_ascii=False), "errors", errors)
    if errors > len(CREWS) // 2:  # 절반 이상 실패 = 차단/구조 변경 의심 → 실패로 표시
        sys.exit(1)


if __name__ == "__main__":
    main()
