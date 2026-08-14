# Regression Review Reference

Goal: prove that everything that worked before the diff still works after it. This is
the pass where "looks fine" is not evidence — you need to trace actual consumers.

## Why agents cause regressions

An agent edits with the context it loaded, which is rarely the whole repository. It will
happily rename a method, tighten a parameter type, or change a return shape and update
only the call sites it happened to have read. The compiler catches some of this in
statically-typed code; it catches none of it across serialization boundaries (JSON
fields, DB documents, API contracts, message queues, reflection, dependency injection by
name, route strings).

## Checklist

For **every changed or removed public symbol** — function, method, class, exported
constant, endpoint route, DTO/response field, config key, environment variable, DB
column/field, event name:

1. **Find all consumers.** Grep for the old name and the new name across the whole repo
   (and note if other repos might consume it — API responses, published packages,
   shared DB documents). A consumer includes: call sites, subclasses/overrides,
   mocks in tests, string references (routes, DI registrations, reflection,
   serialized field names), and documentation the team executes (runbooks, IaC).
2. **Check each consumer against the new signature/shape.** Changed parameter order,
   new required parameter, narrowed type, changed nullability, changed units, changed
   default — each is a behavioral change for some caller.
3. **Serialization boundaries get extra suspicion.** Renaming a property on a type that
   is serialized to JSON/DB changes the wire/storage format. Old stored documents will
   deserialize with the field missing (usually silently null/default). Ask: what happens
   when *existing data* written before this change is read by the new code — and when
   old code (a not-yet-deployed service, a mobile client) reads data written by the new
   code?
4. **Behavioral changes hidden inside "refactors".** Diff the logic, not the shape:
   changed comparison (`<` vs `<=`), changed rounding, changed time zone handling,
   reordered condition with side effects, a filter added/removed from a query, changed
   default value. If the diff claims to be a pure refactor, verify at least the
   critical paths produce identical outputs.
5. **Deleted code.** Anything removed — an endpoint, a case in a switch, a fallback
   branch, an error handler — was presumably there for a reason. Find why it existed
   (git blame, tests, comments) before agreeing it is safe to delete.
6. **Error paths.** A new exception type thrown where callers catch a specific old type;
   an error now swallowed that callers relied on propagating; a changed error message
   that something parses.
7. **Tests as consumers and as evidence.** If tests were *modified* in the same diff to
   make them pass, treat every modified assertion as a suspected behavior change and
   verify it was intended. If tests exist for the changed area, run them.
8. **Concurrency and ordering.** Moved initialization, changed lazy/eager, removed a
   lock, reordered awaits — these regress only under load or race, so they never show
   up in "it works on my machine".

## Severity guidance

- A consumer that demonstrably breaks (compile error, wrong result, unhandled
  exception, wire-format break) → **Failed** (report it first — nothing outranks
  broken behavior).
- A contract change whose consumers you cannot fully enumerate (public API, shared DB,
  cross-repo) → **Failed**, flagged "Needs verification", with the enumeration you did
  manage.
- A modified test assertion without stated intent → **Failed** until explained.
