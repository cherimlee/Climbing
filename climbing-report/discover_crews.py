"""소모임 클라이밍 크루 자동 찾기 (collect.yml에서 하루 한 번 실행)

- 소모임 지역별 클라이밍 모임 목록(/groups/search/<시도>/<시군구>/클라이밍)을 서울·경기·인천 전 지역에서 읽음
  (지역 목록은 소모임 sitemap에서 가져옴)
- 카테고리가 클라이밍(it2=18007)이거나 대표 키워드가 클라이밍인 모임 중 멤버 MIN_MEMBERS명 이상을 crews.json에 추가
- 이미 있는 크루는 멤버 수만 갱신하고 지우지 않음 (손으로 넣은 크루 유지)
- 모임 이름·지역·멤버 수만 읽음. 멤버 개인정보는 읽지 않음
"""
import concurrent.futures, datetime, gzip, json, os, re, sys, time, urllib.parse
import requests

KST = datetime.timezone(datetime.timedelta(hours=9))
BASE = os.path.dirname(os.path.abspath(__file__))
CREWS = os.path.join(BASE, "crews.json")
STAMP = os.path.join(BASE, "crews_discovered.txt")   # 마지막으로 찾은 날짜(KST) — 하루 한 번만 돌게
SITE = "https://www.somoim.co.kr"
SIDO = {"서울특별시": "서울", "경기도": "경기", "인천광역시": "인천"}
MIN_MEMBERS = int(os.environ.get("MIN_MEMBERS", "30"))
DELAY = float(os.environ.get("REQUEST_DELAY", "1.0"))
WORKERS = int(os.environ.get("WORKERS", "4"))
GID = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\d"

S = requests.Session()
S.headers["User-Agent"] = "Mozilla/5.0 (climbing-report personal research)"


def regions():
    """sitemap에 있는 '<시도>/<시군구>/클라이밍' 검색 페이지 목록."""
    r = S.get(f"{SITE}/sitemap/kr/search/sitemap-kr-search.xml.gz", timeout=60)
    r.raise_for_status()
    b = r.content
    try:
        b = gzip.decompress(b)
    except OSError:
        pass
    out = []
    for loc in re.findall(r"<loc>(.*?)</loc>", b.decode("utf-8", "replace")):
        parts = urllib.parse.unquote(loc).split("/groups/search/")[-1].split("/")
        if len(parts) == 3 and parts[0] in SIDO and parts[2] == "클라이밍":
            out.append((parts[0], parts[1]))
    return out


def groups_on(sido, sigungu):
    path = "/groups/search/" + "/".join(urllib.parse.quote(x) for x in (sido, sigungu, "클라이밍"))
    r = S.get(SITE + path, timeout=30)
    r.raise_for_status()
    chunks = re.findall(r'self.__next_f.push\(\[1,"(.*?)"\]\)</script>', r.text, re.S)
    s = "".join(json.loads('"' + x + '"') for x in chunks)
    found = []
    for m in re.finditer(r'"gid":"(' + GID + ')"', s):
        start = s.rfind('{"gn":', 0, m.start())   # 모임 객체 시작
        if start < 0:
            continue
        try:
            g = json.JSONDecoder().raw_decode(s[start:])[0]
        except ValueError:
            continue
        found.append(g)
    return found


def is_climbing(g):
    return g.get("it2") == "18007" or g.get("keyword") == "클라이밍"


def main():
    today = datetime.datetime.now(KST).strftime("%Y-%m-%d")
    if os.environ.get("FORCE") != "1" and os.path.exists(STAMP) and open(STAMP).read().strip() == today:
        print("crews already discovered today — skip")
        return
    crews = json.load(open(CREWS, encoding="utf-8"))
    by_id = {c["crew_id"]: c for c in crews}
    regs = regions()
    print(f"{len(regs)} regions", flush=True)

    seen, errors = {}, 0

    def one(rg):
        nonlocal errors
        try:
            gs = groups_on(*rg)
        except Exception as ex:
            errors += 1
            print("WARN", rg, ex, file=sys.stderr)
            gs = []
        time.sleep(DELAY)
        return gs

    with concurrent.futures.ThreadPoolExecutor(max_workers=WORKERS) as ex:
        for gs in ex.map(one, regs):
            for g in gs:
                seen[g["gid"]] = g
    if errors > len(regs) // 2:
        sys.exit(f"too many errors ({errors}/{len(regs)}) — crews.json unchanged")

    added = 0
    for gid, g in seen.items():
        sido = SIDO.get(g.get("loc1n"))
        members = g.get("gmc") or 0
        if gid in by_id:
            by_id[gid]["members"] = members
            continue
        if not sido or not is_climbing(g) or members < MIN_MEMBERS:
            continue
        sigungu = (g.get("loc2n") or "").split(" ")[-1]
        crew = {"crew_id": gid, "name": g.get("gn", "").strip(), "url": f"{SITE}/{gid}", "members": members,
                "sido": sido, "sigungu": sigungu, "found": today}
        crews.append(crew)
        by_id[gid] = crew
        added += 1
        print("NEW", members, sido, sigungu, crew["name"])
    crews.sort(key=lambda c: -(c.get("members") or 0))
    json.dump(crews, open(CREWS, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    open(STAMP, "w").write(today + "\n")
    known = sum(1 for c in crews if c["crew_id"] in seen and "found" not in c)
    print(f"existing crews also found in search: {known}/{sum('found' not in c for c in crews)}")
    sizes = sorted((g.get("gmc") or 0) for g in seen.values() if is_climbing(g) and SIDO.get(g.get("loc1n")))
    print("climbing group sizes (서울·경기·인천):", len(sizes), "≥30:", sum(x >= 30 for x in sizes), "≥10:", sum(x >= 10 for x in sizes), sizes[:40])
    print(f"climbing groups seen {sum(is_climbing(g) for g in seen.values())}, added {added}, total crews {len(crews)}")


if __name__ == "__main__":
    main()
