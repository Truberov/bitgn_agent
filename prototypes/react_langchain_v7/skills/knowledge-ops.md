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
  1. Identify the file containing the data (e.g., `docs/channels/Telegram.txt`).
  2. Read the file in chunks (e.g., `start_line=1, end_line=200`, then `201-400`,
     etc.) until you reach the end. Do NOT stop at the first chunk.
  3. Count ONLY lines that match the specific marker (e.g., `- blacklist`), not
     total lines — the file may contain headers, blank lines, or other entries.
  4. Sum counts across all chunks for the final answer.
  5. `search()` with `limit=1000` may miss entries in large files — prefer direct
     reads for accurate counts.

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
