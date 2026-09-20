# Decide which Person relationships publish and their semantics

Type: grilling
Status: open
Blocked by: none (02 and 03 resolved 2026-09-20)

## Question

Legacy publishes `IS_INSIDER` (Person → issuer), `HOLDS` (Person →
security, from the transaction tables), `EMPLOYED_BY` (Person → issuer,
from proxy/8-K), and `IS_PERSON_OF` (Person → adviser). Clean MDM's
`domain-model.md` row 62 replaces `IS_PERSON_OF` with same-ID Adviser
profile membership. For each remaining edge: is it kept under the same name
with dated validity and filing provenance; is it published only when both
endpoints are accepted (a Person and an accepted Company/Security); and
what retires it — an explicit later filing, or never by absence?
