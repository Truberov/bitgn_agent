# Skill: Document Ops

Use this skill when creating, organizing, or structuring records — invoices,
reminders, notes, or other typed documents.

## Creating records
- Read the relevant folder README before creating any record.
  It defines required fields, file format, and naming conventions.
- Omit optional fields rather than refusing. Only decline if a truly required
  field (marked as non-optional in the README) is missing.
- When a numbering or sequencing protocol is defined (e.g. a seq.json file):
  1. Read the seq file to get the current value N.
  2. Create the record as filename N (using the format from the README).
  3. Update the seq file to N+1.
  Never skip the seq file update. Never guess the next number.

## Deduplication
- Before creating a record, check if a matching record already exists.
- If it exists and the task is to create it, flag the duplicate instead of
  creating a second copy.

## Organizing records
- Follow the folder structure and naming conventions in the README.
- Do not create folders or naming schemes that deviate from existing patterns.
