"""One TSV line per Level 1 record with the columns the joins need.

Line-based on GLEIF's 4-space pretty print (no JSON parse), so it is fast; the
ijson profile is the cross-check on counts.
Columns: LEI, EntityCategory, EntityStatus, RegistrationStatus,
RegistrationAuthorityID, RegistrationAuthorityEntityID, EntityLegalFormCode,
OtherLegalForm, HQ PostalCode present (1/0), LegalName
"""

import sys
import zipfile

WANT = {
    b'    "LEI": {\n': "lei",
    b'        "EntityCategory": {\n': "cat",
    b'        "EntityStatus": {\n': "est",
    b'        "RegistrationStatus": {\n': "rst",
    b'            "RegistrationAuthorityID": {\n': "ra",
    b'            "RegistrationAuthorityEntityID": {\n': "raid",
    b'            "EntityLegalFormCode": {\n': "lf",
    b'            "OtherLegalForm": {\n': "olf",
    b'        "LegalName": {\n': "name",
}
COLS = ["lei", "cat", "est", "rst", "ra", "raid", "lf", "olf", "name"]


def main(path, out):
    rec: dict = {}
    want = None
    n = 0
    with zipfile.ZipFile(path) as z, z.open(z.infolist()[0]) as f, open(out, "w") as o:
        def flush():
            if rec.get("lei"):
                o.write("\t".join(rec.get(c, "").replace("\t", " ") for c in COLS) + "\n")

        for line in f:
            if line == b"{\n":
                flush()
                rec = {}
                n += 1
                want = None
                continue
            if want is not None:
                s = line.strip()
                if s.startswith(b'"$": "'):
                    rec[want] = s[6:-1].decode("utf-8", "replace")
                    want = None
                    continue
                if s.startswith(b'"@xml:lang"'):
                    continue  # LegalName: language attribute comes before "$"
                want = None
            key = WANT.get(line)
            if key and key not in rec:
                want = key
        flush()
    print(n, file=sys.stderr)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
