"""Line-based pass over Level 1: is AdditionalAddressLine ever an object, is ValidationSources ever a list."""
import io, sys, zipfile, json, collections
c = collections.Counter()
section = None
with zipfile.ZipFile(sys.argv[1]) as z:
    f = io.BufferedReader(z.open(z.infolist()[0]), buffer_size=4 << 20)
    for line in f:
        s = line.strip()
        if s.startswith(b'"LegalAddress"'): section = "legal"
        elif s.startswith(b'"HeadquartersAddress"'): section = "hq"
        elif s.startswith(b'"OtherAddresses"') or s.startswith(b'"TransliteratedOtherAddresses"'): section = "other"
        elif s.startswith(b'"AdditionalAddressLine"'):
            c[f"{section}:AdditionalAddressLine:{'list' if s.endswith(b'[') else 'object' if s.endswith(b'{') else s[-10:].decode()}"] += 1
        elif s.startswith(b'"ValidationSources"'):
            c[f"ValidationSources:{'list' if s.endswith(b'[') else 'object' if s.endswith(b'{') else s[-10:].decode()}"] += 1
        elif s.startswith(b'"ValidationAuthority"') or s.startswith(b'"Registration"'):
            section = None
print(json.dumps(dict(c), indent=1))
