# Company downstream data audit

**Status: IN PROGRESS.** Audit every mastered Company through all configured
downstream fields and relationship paths, then turn only evidence-backed
defects into repeatable data-quality checks. This covers MDM and Silver; Gold
is out of scope.

## Work

- [01 — Trace Company fields and relationships, then define data-quality checks](issues/01-company-field-and-relationship-quality-checks.md)

Use the existing AAPL trace as the control case. Follow the same configured
source, master, relationship, and downstream paths for the full Company
population. Check definitions must follow this repository's data-quality
engine and may use DataKitchen TestGen as a reference for check categories;
TestGen is not a runtime dependency.
