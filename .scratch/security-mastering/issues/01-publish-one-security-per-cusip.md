# 01: Publish one Security per 13F CUSIP

**What to build:** A caller can hand in 13F holdings for one issuer and get back one Security per CUSIP. Alphabet Class A and Class C are two Securities. The Security Title is Class A, Class C, or Option. A title that names neither waits. Each holding still shows the title and issuer name the manager wrote. No Company is created.

**Blocked by:** None (can start immediately).

**Status:** done

- [x] `02079K305` filed as `CAP STK CL A`, `CL A`, and `COM`, under both `ALPHABET INC` and `GOOGLE INC`, is one Security titled Class A.
- [x] `02079K107` filed as `CAP STK CL C` is a second Security titled Class C.
- [x] `02079K907` filed as `OPTIONS` is a third Security titled Option, not Class A.
- [x] A CUSIP whose titles are only `COM` has no Security Title yet.
- [x] Every holding keeps its filed title and filed issuer name.
