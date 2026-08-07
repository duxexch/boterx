---
name: Boterx repo structure
description: Where the actual production files live vs the boterx/ subdirectory in this workspace
---

The git repo (.git) is at /home/runner/workspace/ (workspace ROOT), not inside boterx/.
All production files — comprehensive_bot.py, dashboard/, bot_utils/, handlers/, etc. — live at the workspace root.
The /home/runner/workspace/boterx/ directory was a working/scratch area used during analysis, not the canonical source.

**Why:** The remote (github.com/duxexch/boterx) was created with files at root level. The zip extraction went into boterx/ but the live repo structure is flat.

**How to apply:** When making changes to the Boterx project, always work at /home/runner/workspace/ and commit from there. Git commands from inside boterx/ will use the workspace-level .git and may behave unexpectedly.
