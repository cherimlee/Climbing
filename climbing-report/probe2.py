import gzip, re, sys, json, requests, urllib.parse
S = requests.Session(); S.headers["User-Agent"] = "Mozilla/5.0 (climbing-report personal research)"
for sm in ["search", "curated", "group"]:
    u = f"https://www.somoim.co.kr/sitemap/kr/{sm}/sitemap-kr-{sm}.xml.gz"
    r = S.get(u, timeout=60); b = r.content
    try: b = gzip.decompress(b)
    except Exception: pass
    t = b.decode("utf-8", "replace"); locs = re.findall(r"<loc>(.*?)</loc>", t)
    dec = [urllib.parse.unquote(x) for x in locs]
    print("=====", sm, r.status_code, len(t), "locs", len(locs)); print("SAMPLE", dec[:8])
    hit = [x for x in dec if "클라이밍" in x or "볼더" in x or "climb" in x.lower()]
    print("CLIMB", len(hit), hit[:40])
for q in ["/groups/search?keyword=클라이밍", "/groups/search?q=클라이밍", "/groups/search?query=클라이밍", "/groups/search?search=클라이밍"]:
    r = S.get("https://www.somoim.co.kr" + q, timeout=30); h = r.text
    ids = sorted(set(re.findall(r'/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\d)"', h)))
    txt = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", re.sub(r"<script.*?</script>", "", h, flags=re.S)))
    print("=====", q, r.status_code, len(h), "ids", len(ids), "climbtext", txt.count("클라이밍")); print(txt[:400])
