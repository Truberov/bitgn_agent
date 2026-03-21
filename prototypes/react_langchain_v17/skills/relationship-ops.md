# Skill: Relationship Ops

Use this skill when tracing connections between entities: who belongs to which
account, which contacts are linked to which company, what projects are connected.

## Tracing relationships
- Follow ID references explicitly: read the record that contains the ID, then
  read the referenced record. Do not infer relationships from names alone.
- Account → contact: use the primary_contact_id field in the account record.
- Contact → account: use the account_id field in the contact record.

## Ambiguity
- If multiple entities share the same name, list all of them with their
  distinguishing details (IDs, accounts, roles) and ask the user to specify.
  Never guess which one was meant.

## Scope of relationships
- Only report relationships that are explicitly recorded in the repository.
  Do not infer or assume connections that are not present in the data.
