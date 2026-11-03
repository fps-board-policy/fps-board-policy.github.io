# How to update a board policy

Use this after the Board approves a new, revised or rescinded policy. You need your own GitHub login with editor access to **fps-board-policy**.

## Before you upload: check the Word file

Every policy file should follow the same layout, or the website may show it wrong.

- **Filename** starts with the policy number, then the title: `5415 Anti-Bullying Policy.docx`
- **First line** of the document: the series name, for example `Students` or `Bylaws of the Board - Meetings`
- **Second line:** the policy title
- **At the end:** `Legal Reference:` lines (if any), then `Date of Adoption: June 8, 2026`, and `Revised: …` / `Reviewed: …` lines when they apply. Write dates as *Month Day, Year*.
- Accept all tracked changes and remove comments and highlighting.
- If the policy is new, also add it to that section's index file.

## Replace a revised policy

1. Sign in at **github.com** and open **github.com/fps-board-policy/fps-board-policy.github.io**.
2. Click the section folder, for example **Section 50 Students**.
3. Click **Add file → Upload files**.
4. Drag in the revised Word file. **Use exactly the same filename** as the old one so it replaces it. If the title changed and you renamed the file, delete the old file afterward (see below).
5. In the box under **Commit changes**, describe the change, for example *Revised 5415 per Board action 11/9/2026*.
6. Click **Commit changes**.

## Add a new policy

Same as above. Upload the new file into the right section folder, and upload the updated section index too.

## Remove a rescinded policy

1. Open the section folder and click the policy's file.
2. Click the **⋯** menu (top right of the file) → **Delete file**.
3. Describe the change (for example *Rescinded 4161 per Board action 11/9/2026*) and click **Commit changes**.

## Check that it worked

1. Click the **Actions** tab at the top of the repository. The newest run shows a yellow dot while it works and a green check when it's done (about 2 minutes). A red ✕ means the build stopped. The old version of the site stays up; ask for help.
2. Click the run, then scroll down to **Policy checks**. It lists anything in the files that needs attention, such as a missing adoption date or a policy missing from its section index.
3. Open **https://fps-board-policy.github.io**, search for the policy number, and confirm the new text and date. If you still see the old version, refresh the page.

## Undo a mistake

Open the file, click **History**, pick the earlier version, and upload that copy again. Every past version is kept.
