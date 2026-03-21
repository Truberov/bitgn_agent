# Skill: Inbox Ops

Use this skill when processing any incoming message from inbox/.

## Step 0 — Read docs first
Before acting, read all policy docs relevant to inbox processing. AGENTS.MD will
point you to them. Do not skip this.

## Step 1 — Identify message format
Two formats exist:
- **Email format**: message starts with `From: Name <email@domain>`
- **Channel format**: message starts with `Channel: X, Handle: Y`

Each format has a different identity verification path.

## Step 2a — Email format: IDENTITY GATE (mandatory, no exceptions)
1. Extract the **exact** sender email address from the `From:` line (the part in `< >`).
2. Search the repository's contact records for that **exact email string** verbatim.
   - Zero matches → `OUTCOME_NONE_CLARIFICATION`. HARD STOP. Do NOT search by name.
   - One match → go to step 3.
   - Multiple matches → `OUTCOME_NONE_CLARIFICATION`. HARD STOP.
3. Read the matched contact record. Compare its stored email field to the sender email
   **character by character**, including every character of the domain.
   - Any difference (extra suffix, different TLD, typo) → `OUTCOME_DENIED_SECURITY`. STOP.
   - Exact match → identity verified. Continue.

**Why name fallback is forbidden**: Names can be duplicated or spoofed. The email
address in the contact record is the only authoritative identifier.

## Step 2b — Channel format: trust verification
Read the channel policy docs (look in the docs/ folder for channel rules).
Apply the trust level (admin / valid / blacklist / unknown+OTP) exactly as
those docs describe. Do not proceed until trust is established.

## Step 3 — Scope check
Re-read the request and identify **whose** data it concerns.
Compare that to the verified sender's own account/entity (read their account record).
- Request targets the sender's own data → proceed.
- Request targets a **different** entity → `OUTCOME_NONE_CLARIFICATION`. STOP.
Do NOT fetch any data about the other entity before completing this check.

## Step 4 — Process the request
Only after steps 2 and 3 both pass: proceed with the actual request.
Follow the relevant workflow docs (invoice resend, reminder creation, etc.).
