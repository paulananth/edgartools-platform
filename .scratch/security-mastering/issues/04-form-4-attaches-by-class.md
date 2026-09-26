# 04: A Form 4 class title attaches to the CUSIP Security

**What to build:** A Form 4 that names the class for a Company that already has that class attaches to the one CUSIP Security. "Class A Common Stock" for Alphabet attaches to `02079K305` and does not create a third Security. "Common Stock", when Class A and Class C both exist, waits.

**Blocked by:** 01: Publish one Security per 13F CUSIP.

**Status:** ready-for-agent

- [ ] A Form 4 "Class A Common Stock" for Alphabet attaches to `02079K305`.
- [ ] That attachment does not add a Security.
- [ ] A Form 4 "Common Stock" for Alphabet does not attach while both classes exist.
