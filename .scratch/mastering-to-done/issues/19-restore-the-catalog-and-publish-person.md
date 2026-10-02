# Restore the catalog and publish Person and links

Type: task
Status: open
Blocked by: 11, 18

## Question

1. **Bring back the local OpenMetadata stack.** Find where its compose file lives; it was not in the repo when removed on 2026-10-01. Either restore the catalog volumes from the 2026-10-02 backups, or start clean and republish. Starting clean is likely simpler, since `rules catalog` publishes everything from the rules.
2. **Republish with `rules catalog`.** Person, the link types and the quality checks must show; extend the publisher if links aren't covered yet.
3. **Regenerate the Mapping Documents** (`rules mapdoc`) for Person and the link sources.

Check in the catalog UI and in the generated spreadsheets that each new field and link type appears.
