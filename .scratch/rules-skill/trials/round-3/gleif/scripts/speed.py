import sys, time, zipfile
path = sys.argv[1]
t = time.time(); n = 0; lines = 0
with zipfile.ZipFile(path) as z:
    info = z.infolist()[0]
    with z.open(info) as f:
        while chunk := f.read(8 * 1024 * 1024):
            n += len(chunk); lines += chunk.count(b"\n")
print(info.filename, n, lines, round(time.time() - t, 1), "s")
