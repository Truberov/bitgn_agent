# Skill: Knowledge Ops

Use this skill when retrieving information about people, projects, dates, or
recent activity — factual lookup and recall tasks.

## Retrieval principles
- Always use tools to look up data. Never answer from memory or assumption.
- When searching for a person by name, try multiple orderings (first last, last
  first) and also search each part separately.
- When a question involves a date ("X days ago", "last seen", "captured on"):
  1. Call `context()` FIRST to get the repository's current date.
  2. Compute the target date from that — not from any assumed or system date.
  3. Then search for records matching that exact date.

## Counting and exhaustive reads
- When the task requires counting items (entries, lines, accounts, records):
  1. Read the full file. If the file is large, read it in chunks using
     `start_line`/`end_line` until you have reached the last line.
  2. Count only after you have read all content — never count from a partial read.
  3. Use `search()` with a high limit (e.g., `limit=1000`) to catch all matches.

## When data is missing
- If a search returns no results, try at least two alternative approaches
  (different search terms, different folder, tree to locate the right path).
- If data is genuinely missing after exhaustive search → OUTCOME_NONE_CLARIFICATION.
- If a relative date maps to a date for which no record exists →
  OUTCOME_NONE_CLARIFICATION (do not substitute the nearest record).

## Answering precisely
- Answer only what was asked. Do not add context unless requested.
- When the task says "answer only with X", return exactly that — nothing more.
- Verify data from the record before including it in the answer.
