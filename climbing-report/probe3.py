import re, json, requests, urllib.parse
S = requests.Session(); S.headers["User-Agent"] = "Mozilla/5.0 (climbing-report personal research)"
def flight(h):
    out = []
    for x in re.findall(r'self.__next_f.push\(\[1,"(.*?)"\]\)</script>', h, re.S):
        try: out.append(json.loads('"' + x + '"'))
        except Exception: pass
    return "".join(out)
for path in ["/groups/search/서울특별시/마포구/클라이밍", "/groups/search/경기도/성남시/클라이밍", "/운동-스포츠/클라이밍", "/강남-클라이밍-모임"]:
    r = S.get("https://www.somoim.co.kr" + urllib.parse.quote(path), timeout=30); h = r.text; s = flight(h)
    ids = re.findall(r'"/?([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\d)', h)
    print("=====", path, r.status_code, len(h), "uniq ids", len(set(ids)))
    # find dict-like objects containing a group id and a name
    for m in list(re.finditer(r'\{"[a-z_0-9]+":[^{}]{0,1500}?"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\d"[^{}]{0,1500}\}', s))[:3]:
        print("OBJ", m.group(0)[:700])
    txt = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " | ", re.sub(r"<script.*?</script>", "", h, flags=re.S)))
    i = txt.find("모임"); print("TXT", txt[1500:3500])
