# Performance Review

Goal: find work the code does that it doesn't need to do — especially work that grows
with data size or traffic. Judge against realistic production scale, not the developer's
test data: a pattern that is fine for 10 rows and catastrophic for 100,000 is a defect
*now*, because data only grows.

## The high-yield patterns

Ordered roughly by how often agent-written code contains them:

1. **I/O inside a loop (N+1).** A query, HTTP call, file read, or cache round-trip
   executed per item of a collection. The fix is almost always a batched form: one query
   with an `IN`/join, a bulk API, `Promise.all`/`Task.WhenAll` with a bounded degree of
   parallelism. Look for: `foreach`/`for`/`map` bodies containing `await`, repository
   calls keyed by a single id inside iteration, lazy-loaded ORM navigation properties
   accessed in a loop.
2. **Fetching everything to use a little.** `SELECT *` / full-document reads when two
   fields are needed; loading a whole table/container and filtering in application code;
   reading a file fully to check its first line. The database/service can almost always
   do the filtering, projection, and aggregation server-side.
3. **Missing pagination / unbounded reads.** Any query without a `TOP`/`LIMIT`/
   continuation handling that runs against a collection that grows over time. It works
   in test, then one day it is a timeout and an OOM.
4. **Sync-over-async and serialized awaits.** `.Result`/`.Wait()`/`GetAwaiter()
   .GetResult()` on async code (thread-pool starvation, deadlock risk); independent
   awaits executed sequentially when they could run concurrently.
5. **Repeated computation of an invariant.** The same parse, regex compile, config
   read, or query executed on every call/iteration when it could be computed once,
   cached, or hoisted out of the loop.
6. **Accidental quadratic behavior.** `list.Contains`/`indexOf` inside a loop over
   another list (use a set/dictionary); string concatenation in a loop (use a
   builder/join); repeated `Array.prototype.shift`/`unshift` on large arrays.
7. **Memory pressure.** Materializing large sequences (`ToList()` on a streaming
   source) just to iterate once; buffering a whole file/response body when streaming is
   available; holding large objects in long-lived caches without eviction.
8. **Chatty caching.** A cache added by the agent that is checked *after* doing the
   expensive work, keyed so broadly it never hits, or never invalidated (which is a
   correctness bug too).

## How to verify a performance finding

State the scaling story concretely: what is N, where does N come from in production,
and what happens per N. "This calls the repository once per vessel; the fleet endpoint
serves ~500 vessels, so one request issues ~500 queries" is a finding. "This might be
slow" is not — either establish the scale or drop it.

If the loop bound is provably small and fixed (e.g., iterating over 7 weekdays), an N+1
there is a low-priority **Warning** at most — often not worth reporting. Severity
follows the realistic N and the request rate of the code path, not the pattern's name.

## Severity guidance

- Unbounded read / N+1 on a growing collection in a hot path → **Failed** (and say so
  in the finding when it also multiplies metered cost — see `cost.md`).
- Sync-over-async in a request path → **Failed**.
- Hoistable computation, quadratic on small-N, missed concurrency → **Warning**.
