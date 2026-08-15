# Fixture review

The seeded query implementation fails the performance requirement.

```json
{
  "verdict": "fail",
  "findings": [
    {
      "severity": "failed",
      "title": "Empty fleet triggers one query per ship",
      "file": "evals/fixtures/sample_project.py",
      "line": 15,
      "confidence": "confirmed",
      "fix_hint": "Batch the lookup before aggregating totals"
    }
  ]
}
```
