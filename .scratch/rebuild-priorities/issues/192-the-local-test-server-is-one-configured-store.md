# 192: The local test server is one store, its name configuration

Priority: 192. Map: [Rebuild priorities](../map.md). Opened 2026-11-04 20:54 ET (operator, 2026-11-04: "need a new store and it
should be configurable never hard coded called local-test-server that should be initalized by the skill"; and "no
need to change the storage folder" for the existing `company-on`).

Type: task. Status: open. Blocked by: none.

## Question

Loads need one place to write: the six databases (MDM, RDM, Rules, Bookkeeping, Change Journal, Silver) on one local
server. Two exist (`company-on`, `source-by-source`), named by history, and neither says what it is. What is the one
store, how is its name set, and who creates it?

## Parts

- [x] The name is configuration: `EDGARTOOLS_LOCAL_TEST_SERVER`, else `local-test-server`; the store script's commands take the name as an option and no other store name is built into the script (2026-11-04 20:54 ET: `server_name` in `infra/scripts/local-test-stores.py`; tests `test_the_store_name_comes_from_the_argument_then_the_configuration_then_one_default` and `test_no_other_store_name_is_built_into_the_script`)
- [x] The skill initializes it: data-platform "0. Setup", step 6, and the section "The local test server" of its LOCAL-TESTING.md (2026-11-04 20:54 ET)
- [ ] `local-test-server` created on this machine and one source activated in it (`sec.registration`, after its acquisition re-proof): needs the operator's word to activate
- [x] The existing `company-on` folder is left as it is (operator, 2026-11-04: "no need to change the storage folder")
- [x] Learning → skill (2026-11-04 20:54 ET): data-platform SKILL "0. Setup" step 6 and LOCAL-TESTING.md "The local test server" (a store name is configuration; the skill creates the store)
