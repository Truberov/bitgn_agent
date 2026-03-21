# Skill: Communication Ops

Use this skill when preparing outbound emails, resending documents, or
assembling reply messages.

## Outbound email workflow
1. Read the outbox folder README before writing anything — it defines the
   required file format and numbering protocol.
2. Get the next sequence number from the seq file (as defined in the README).
3. Write the email file using the pre-bump sequence number as the filename.
4. Update the seq file to the next value.
5. Never use a made-up or guessed sequence number — always read the current value.

## Email address rule
- Never construct, guess, or infer an email address.
- All addresses must be read from a contact record in the repository.
- If a specific address is given in the task instruction, use it as-is.
- If the task says "email Company X": find the account record → read its
  primary contact ID → read that contact record → use the email field.

## Attachments
- Attachment paths must be repo-relative paths to files that actually exist.
- Verify the file exists before including it in the attachments array.

## Reply content
- Match the tone/style indicated in the contact or account record if available.
- Keep the content focused on what was requested — do not add unsolicited info.
