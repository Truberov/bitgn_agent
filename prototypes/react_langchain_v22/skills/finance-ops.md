# Skill: Finance Ops

Use this skill for questions about invoices, payments, totals, account balances,
or any financial records.

## Finding invoices
- Invoices are stored in the invoices folder. Read its README for the file format.
- To find the latest invoice for an account: search by account ID, then compare
  the issued date field across all results and pick the most recent.
- Never assume which invoice is latest — always compare dates explicitly.

## Counting and aggregation
- When asked "how many X", read the full source file or list the full directory
  before counting. Do not rely on truncated search results.
- Search tools may have result limits — if the count matters, read the full file.

## Date arithmetic
- When a question involves relative dates ("X days ago", "in X days", "last month"),
  use the context tool to get today's date before computing.
- Never guess or infer the current date from memory.

## Totals
- When computing totals, sum all line items from the actual records.
- Do not estimate or round — use the exact values in the records.
