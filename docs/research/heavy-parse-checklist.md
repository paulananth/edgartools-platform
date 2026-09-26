# Heavy 13F rules parse

The S3 list is done. Companyfacts and GLEIF are absent. ADV bulk is 14 ZIPs. The comparison is the pinned 13F information tables only.

- [x] List bronze keys and sizes. No download. (2026-09-25)
- [x] Drop companyfacts (empty prefix), GLEIF (empty prefix), and ADV bulk (14 files).
- [x] Pin the 100 and 1,000 largest information tables whose file name is `infotable.xml`, `informationtable.xml`, or `form13finfotable.xml`. 1.43 GiB, under the 20 GiB stop.
- [x] Download that pin once, keyed by ETag. No SEC requests. 1,000 files, 2026-09-25.
- [x] Source Contract for one `infoTable` row, read by the prototype rules engine. Root match uses the XML local name.
- [x] Compare 100 artifacts with `parse_thirteenf`. 100/100 match, 1,249,612 rows. (2026-09-25)
- [x] Compare the same 1,000. First pass: 989 match, 11 titles were the literal `None`. After the contract blanks `none` and `nan` the same way `parse_thirteenf` does: 1,000/1,000 match, 2,955,223 rows. (2026-09-25)
- [x] Write `heavy-parse-compare-100-1000.md` with the pin, the match, and the times.
- [x] Leave the production parser in place. The rows match. The prototype rules reader is slower, so it does not replace `parse_thirteenf` on this evidence.
