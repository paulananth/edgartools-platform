# Research NAICS/GICS/alternative classification systems for MDM companies

Type: research
Status: claimed

## Question

Which industry classification system(s) beyond SIC should EdgarTools
Platform add for MDM companies -- NAICS, GICS, another candidate (e.g.
ISIC), or a combination -- and what does actually sourcing per-company
codes for that system look like?

Cover, for each candidate system (at minimum NAICS and GICS):

1. **Licensing.** Is the classification's structure/taxonomy itself
   freely usable and redistributable (NAICS: yes, US Census Bureau
   public standard), or does it require a data license (GICS: owned by
   S&P/MSCI -- confirm current licensing terms and whether a no-cost or
   low-cost tier exists for a project at this platform's scale)?
2. **Per-company data source.** A classification's TAXONOMY (the code
   list itself) is a separate question from actually knowing which code
   applies to a given company. For each system: does SEC/EDGAR already
   capture and expose a per-filer code anywhere (e.g. some forms have a
   NAICS field on their cover page -- confirm which forms, how populated
   coverage is), or would per-company codes require an external
   crosswalk/vendor dataset? A SIC-to-NAICS public crosswalk table
   exists (US Census Bureau) -- is deriving NAICS from the SIC code
   EdgarTools already has a viable path, and how lossy/ambiguous is that
   mapping (SIC and NAICS don't have a clean 1:1 correspondence)?
3. **Structure/hierarchy.** Is the system flat (like SIC's 4-digit code)
   or tiered (NAICS: 2-6 digit sector/subsector/industry-group/industry/
   national-industry; GICS: sector/industry-group/industry/
   sub-industry)? This affects the "where does it live" design question
   this map has deferred to fog.
4. **Real-world usage.** Which system(s) do peer financial-data platforms
   and typical downstream consumers (dashboards, screening tools,
   industry comparison) actually expect/use in practice -- does this
   favor one system over another for this platform's actual audience?

## Answer

<!-- filled in on resolution -->
