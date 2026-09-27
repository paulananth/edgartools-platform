"""Line-based pass: top-level LEI values failing ISO 17442 mod 97 (and the category nearby)."""
import io, re, sys, zipfile, json
LEI_RE = re.compile(r"[A-Z0-9]{18}[0-9]{2}")
def ok(v):
    if not LEI_RE.fullmatch(v): return False
    return int("".join(str(ord(c)-55) if c.isalpha() else c for c in v)) % 97 == 1
path, key = sys.argv[1], sys.argv[2].encode()
bad, n = [], 0
with zipfile.ZipFile(path) as z:
    f = io.BufferedReader(z.open(z.infolist()[0]), buffer_size=4 << 20)
    grab = False
    for line in f:
        if grab:
            v = line.split(b'"')[-2].decode(); n += 1; grab = False
            if not ok(v): bad.append(v)
        elif line.startswith(key):
            grab = True
print(json.dumps({"checked": n, "bad": len(bad), "examples": bad[:25]}))
