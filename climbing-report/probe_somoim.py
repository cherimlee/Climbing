import re, sys, json, requests
S = requests.Session(); S.headers["User-Agent"] = "Mozilla/5.0 (climbing-report personal research)"
def flight(h):
    ch = re.findall(r'self.__next_f.push\(\[1,"(.*?)"\]\)</script>', h, re.S)
    out = []
    for x in ch:
        try: out.append(json.loads('"' + x + '"'))
        except Exception: pass
    return "".join(out)
for u in sys.argv[1:]:
    try:
        r = S.get(u, timeout=30)
    except Exception as e:
        print("ERR", u, e); continue
    h = r.text; s = flight(h)
    print("=====", u, r.status_code, len(h), "flight", len(s), "final", r.url)
    hrefs = sorted(set(re.findall(r'href="([^"#]+)"', h)))
    print("HREFS", [x for x in hrefs if not x.endswith(('.css', '.js', '.png', '.ico', '.svg'))][:80])
    print("APIS", sorted(set(re.findall(r'https?://[a-z0-9.-]*somoim[a-z0-9.-]*/[^"\'\\\s<>]{0,80}', h + s)))[:60])
    print("PATHS", sorted(set(re.findall(r'"(/(?:api|search|category|ctg|list|group|groups|meetup)[^"\\]{0,60})"', h + s)))[:60])
    ids = sorted(set(re.findall(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\d?', h + s)))
    print("UUIDS", len(ids), ids[:10])
    i = s.find('"group":{')
    if i >= 0: print("GROUPKEYS", list(json.JSONDecoder().raw_decode(s[i+8:])[0].keys())[:80])
    print("TEXT", re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", re.sub(r"<script.*?</script>", "", h, flags=re.S)))[:600])
