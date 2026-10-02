"""climbing_gyms.json(원본) → map.html 안의 암장 데이터와 gyms.json을 다시 만든다.

암장 정보는 docs/data/climbing_gyms.json 한 곳에서만 고치고, 고친 뒤 이 스크립트를 실행하세요.
    python sync_map_data.py          # map.html·gyms.json 갱신
    python sync_map_data.py --check  # 갱신이 필요한지만 확인 (필요하면 종료 코드 1)

- 지도에는 폐업·폐업추정과 좌표 없는 암장을 빼고 넣는다.
- 지도에 안 쓰는 필드(updated, kakao_id, address_jibun)와 빈 값은 빼고, 출처 링크는 4개까지만 넣는다.
- 상단 카드의 'YYYY.M.D 조사' 날짜는 updated 중 가장 최근 날짜로 맞춘다.
"""
import json, os, re, sys

BASE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(BASE, "docs", "data", "climbing_gyms.json")
MAP = os.path.join(BASE, "docs", "map.html")
GYMS = os.path.join(BASE, "gyms.json")

HIDE_STATUS = {"폐업", "폐업추정"}
DROP_FIELDS = {"updated", "kakao_id", "address_jibun"}
MAX_SOURCES = 4


def map_entry(g):
    out = {}
    for k, v in g.items():
        if k in DROP_FIELDS or v in (None, "", []):
            continue
        out[k] = v[:MAX_SOURCES] if k == "sources" else v
    return out


def build(src):
    on_map = [map_entry(g) for g in src if g.get("status") not in HIDE_STATUS and g.get("lat") is not None and g.get("lng") is not None]
    gym_data = json.dumps(on_map, ensure_ascii=False, separators=(",", ":"))
    gyms = json.dumps([{k: g.get(k) for k in ("id", "name", "sido", "sigungu", "lat", "lng", "status")} for g in src], ensure_ascii=False, indent=1)
    dates = [g["updated"] for g in src if g.get("updated")]
    return on_map, gym_data, gyms, max(dates) if dates else None


def main():
    check = "--check" in sys.argv
    src = json.load(open(SRC, encoding="utf-8"))
    ids = [g["id"] for g in src]
    if len(ids) != len(set(ids)):
        sys.exit("climbing_gyms.json에 같은 id가 두 번 이상 있어요: " + ", ".join(sorted({i for i in ids if ids.count(i) > 1})))
    on_map, gym_data, gyms, latest = build(src)

    html = open(MAP, encoding="utf-8").read()
    pat = re.compile(r'(<script type="application/json" id="gymData">)(.*?)(</script>)', re.S)
    if not pat.search(html):
        sys.exit("map.html에서 gymData 블록을 찾지 못했어요.")
    new_html = pat.sub(lambda m: m.group(1) + gym_data + m.group(3), html, count=1)
    if latest:
        y, mo, d = latest.split("-")
        new_html = re.sub(r"\d{4}\.\d{1,2}\.\d{1,2} 조사", f"{y}.{int(mo)}.{int(d)} 조사", new_html, count=1)

    old_gyms = open(GYMS, encoding="utf-8").read() if os.path.exists(GYMS) else ""
    stale = [name for name, old, new in (("map.html", html, new_html), ("gyms.json", old_gyms, gyms)) if old != new]
    if check:
        if stale:
            sys.exit("climbing_gyms.json과 맞지 않아요: " + ", ".join(stale) + " → python sync_map_data.py 를 실행하세요.")
        print("map.html·gyms.json이 climbing_gyms.json과 같아요.")
        return
    if "map.html" in stale:
        open(MAP, "w", encoding="utf-8", newline="").write(new_html)
    if "gyms.json" in stale:
        open(GYMS, "w", encoding="utf-8", newline="").write(gyms)
    print(f"지도에 {len(on_map)}곳 / 전체 {len(src)}곳 · 바뀐 파일: {', '.join(stale) or '없음'}")


if __name__ == "__main__":
    main()
