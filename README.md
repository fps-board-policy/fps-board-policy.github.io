# FPS Board Policy

Source files for the Fremont Public Schools Board Policy website:
**https://fps-board-policy.github.io**

## What's here

| Folder | What it holds |
|---|---|
| `Section 10 …` to `Section 90 …` | The official Word files, one per policy, plus each section's index. **This is the only place staff edit.** |
| `tools/` | The converter and the website template. Leave these alone unless you are changing how the site works. |
| `.github/workflows/` | The automatic rebuild. Runs every time a file changes. |

## How the site updates

1. An authorized editor uploads, replaces or deletes a Word file in a section folder.
2. GitHub converts every file, checks it, and rebuilds the site (about 2 minutes).
3. The new version is live at the address above.

Step-by-step instructions for staff: **[HOW_TO_UPDATE.md](HOW_TO_UPDATE.md)**

## Who can change content

Only members of the `fps-board-policy` organization with write access. Everyone else can only read. Every change is recorded with who made it and when, and any earlier version can be restored from the file's **History**.
