# Skill: Relationship Ops

Use this skill when tracing connections between entities: who belongs to which
account, which contacts are linked to which company, what projects are connected.

## Tracing relationships
- Follow ID references explicitly: read the record that contains the ID, then
  read the referenced record. Do not infer relationships from names alone.
- Account → contact: use the primary_contact_id field in the account record.
- Contact → account: use the account_id field in the contact record.
- Account → account_manager email: the `account_manager` field holds a person's
  name (string), not an ID. To get their email:
  1. Search `contacts/` for that exact name (try both orderings).
  2. Manager records may be in `contacts/mgr_*.json` — include that pattern.
  3. Read the matching contact record and return its `email` field.

## Returning data from records
- When asked for account names: read each account JSON and return the `name`
  field — do NOT return file names, IDs, or counts.
- When asked for an email: return the exact `email` field value from the contact
  record — do NOT construct or guess addresses.
- When asked for attributes described in notes/description (e.g. "weak internal
  sponsorship", "seeded for duplicate-contact ambiguity"): search the `notes`
  field specifically, then verify all qualifiers match before proceeding.

## Ambiguity
- If multiple entities share the same name, list all of them with their
  distinguishing details (IDs, accounts, roles) and ask the user to specify.
  Never guess which one was meant.

## Scope of relationships
- Only report relationships that are explicitly recorded in the repository.
  Do not infer or assume connections that are not present in the data.
