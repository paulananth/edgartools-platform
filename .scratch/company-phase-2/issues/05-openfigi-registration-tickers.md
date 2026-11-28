# OpenFIGI: the registration tickers MDM lacks

Status: open
Type: task
Owner: claude (map decision 11; operator's permission for this OpenFIGI request, 2026-11-27: "agreed")

A third OpenFIGI input beside N-PORT and Form 4: the registration and prospectus tickers no Security holds (about 372). A
ticker OpenFIGI does not know is Set Aside as "not listed".

## Checklist

- [ ] The input in `sources/openfigi/inputs.yaml` and its load job; the ticker list written from silver, counts only in the repo
- [ ] The capture (about 4 batch calls), within the permission given
- [ ] Tests for the input's selection
- [ ] `/code-review`
- [ ] Learning → skill
