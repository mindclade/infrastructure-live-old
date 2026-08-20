# Failed production apply

1. Stop further applies through workflow concurrency/freeze controls.
2. Preserve the exact commit, logs, unit list, and plan evidence.
3. Determine whether the failure occurred before or after a provider mutation.
4. Run a read-only refresh plan for the affected units; do not edit state by hand.
5. Prefer a reviewed forward fix. Restore state only for proven state corruption.
6. Re-run through the protected production environment and publish an incident summary.
