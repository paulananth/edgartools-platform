import glob
for f in glob.glob("*.raw"):
    b=open(f,'rb').read()
    try: s=b.decode('utf-8')
    except UnicodeDecodeError: s=b.decode('cp1252')
    open(f[:-4]+".csv","w").write(s)
