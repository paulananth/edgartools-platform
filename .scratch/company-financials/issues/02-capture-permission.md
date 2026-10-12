# 02 Capture permission and route for company facts

Type: grilling. Status: resolved. Blocked by: none. Map: [map](../map.md).

## Question

How are the cohort's company facts captured: one bounded capture now (about 500 requests to SEC's data API, about a minute at the fair-access rate, local proving folder only, a one-time ruling), or through L8's configured capture worker when it exists? Nothing local or in prod bronze holds company facts or 10-K/10-Q documents.

## Answer

Operator, 2026-10-12 07:50 ET: "a": one bounded capture now from SEC's company facts API, local proving folder only, a one-time ruling; not through L8.
