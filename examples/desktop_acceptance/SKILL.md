---
name: invoice-audit
description: Audit a synthetic invoice and pass verified state to another reviewer.
---

# Invoice audit

This fixture contains no personal or production data.
Invoice INV-DEMO has three line totals: 10, 20 and 30 EUR.

1. Calculate the sum and record the invoice ID, currency and total in state.
2. Store a text evidence artifact containing the arithmetic and its result.
3. The first reviewer transfers the run to a second reviewer without completing it.
4. The second reviewer reads the persistent context and evidence, independently
   checks that the total is 60 EUR, and records a successful review.
5. Complete only after the second review. Never invent an executed external tool.
