# Cloud-Cost Review

Goal: find changes that increase the cloud bill — silently, and in proportion to
traffic or data growth. This pass exists separately from performance because the two
diverge: a query can return in 40 ms (no user notices) while consuming 100× the request
units it should (finance notices at the end of the month). Latency has monitoring;
spend usually doesn't.

## What is metered? (the mental model)

Anything billed **per call, per unit of throughput, or per byte**:

- **Request-unit databases** — Azure Cosmos DB (RUs), DynamoDB (RCU/WCU), BigQuery
  (bytes scanned), serverless SQL. Every query has a price; a bad query costs 100–1000×
  a good one *while returning the same result*.
- **Per-call APIs** — LLM/AI APIs (per token), geocoding/maps, SMS/email, translation,
  third-party data feeds. A retry loop or an N+1 against these multiplies real dollars.
- **Egress** — data leaving a region/zone or the cloud. Cross-region chatter, oversized
  responses, images/blobs proxied through the backend.
- **Log & telemetry ingestion** — Application Insights, Datadog, CloudWatch bill per
  GB ingested. A debug log line inside a per-item loop in production is a cost bug.
- **Storage operations** — blob/S3 requests are billed per operation and per byte;
  list-then-read-each patterns, per-item small writes, and hot small-file churn add up.
- **Serverless invocations** — functions billed per execution × duration × memory; a
  timer that polls when an event trigger exists, or fan-out that re-invokes per item.

## Review checklist

For every touched call site that hits a metered service, ask three questions:

1. **How many times does this run?** Per request? Per item? Per timer tick? Multiply by
   production traffic. Any metered call inside a loop is a finding candidate.
2. **How much does each call scan or transfer?** Not "how much does it return" — metered
   databases charge for what they *scan*. A query returning 3 rows can scan a million.
3. **Does it grow?** With users, vessels, documents, days of history? A cost that is
   flat is a tradeoff; a cost that compounds with data growth is a defect.

Common diff-level red flags:

- A new query without the partition key / hash key in its filter (see deep-dive below).
- A retry policy added without backoff or without a cap, wrapping a per-call-billed API.
- Caching *removed* (or a cache key changed so it never hits) in front of a metered call.
- A new log statement inside a loop, or logging a whole payload/document.
- Polling introduced where a webhook/event/change-feed exists.
- A batch/bulk API replaced by per-item calls (often an agent "simplifying" code).
- LLM calls with an unbounded prompt (whole file/history stuffed into context) or
  without caching for repeated identical inputs.

## Deep-dive: Azure Cosmos DB (the canonical RU database)

Cosmos DB charges request units per operation, and the difference between a good and a
bad access pattern is routinely two to three orders of magnitude. The same reasoning
applies to DynamoDB (partition key ≈ hash key, cross-partition ≈ Scan).

1. **Cross-partition fan-out** — the #1 offense. A query whose `WHERE` does not pin the
   partition key executes on *every physical partition*: `WHERE c.status = 'active'` on
   a container partitioned by `/tenantId` pays RUs per partition, and the cost grows as
   the container grows even if results don't. Check every new/modified query: does the
   filter include the container's partition key? If the partition key isn't visible in
   the diff, find the container definition or ask — this single check is most of the
   value of this file.
2. **Query where a point-read would do.** `ReadItemAsync(id, partitionKey)` costs ~1 RU;
   `SELECT * FROM c WHERE = @id` for the same document costs several times that.
   Reading one known document via a query is a finding.
3. **Unbounded queries.** No `TOP`, no `MaxItemCount`, iterating all continuation pages
   into a list. RU cost scales with documents scanned; combined with cross-partition
   this is the classic "the container grew and now every request costs 10,000 RUs".
4. **`SELECT *` on large documents.** RU charge includes the size of documents read and
   returned. Project only needed fields; better, keep documents small.
5. **Scans from non-indexed predicates.** Filtering or `ORDER BY` on a path excluded
   from the indexing policy, or wrapping the filtered property in a function
   (`UPPER(c.name) = ...`, `CONTAINS`), forces a scan of every document's payload.
6. **Write amplification.** Every upsert re-indexes the whole document; rewriting a
   large document to change one field, or per-item upserts in a loop instead of bulk
   support / batch, multiplies write RUs. Also: updating documents that didn't change
   (no dirty check) bills full write RUs for a no-op.
7. **Change feed / trigger loops.** A change-feed processor that writes back to the
   same container it watches re-triggers itself — RU consumption with no upper bound.

When you flag a Cosmos finding, name the container, its partition key (if you found
it), and the scaling story: "fans out across all partitions of `ship-reports`
(partitioned by `/sk`), scanning grows with fleet size."

## Severity guidance

- Metered call whose cost grows with data size or sits in an unbounded loop
  (cross-partition scan of a growing container, N+1 LLM calls, self-triggering change
  feed) → **Failed**.
- Flat but avoidable overspend (query instead of point-read, `SELECT *`, payload
  logging) → **Failed** in hot paths, **Warning** in cold ones.
- Missed cheap optimization (projection, batch API available) → **Warning**.
