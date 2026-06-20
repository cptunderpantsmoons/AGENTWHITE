# Learnings

## [LRN-20260606-001] knowledge_gap

**Logged**: 2026-06-06T20:30:00Z
**Priority**: medium
**Status**: pending
**Area**: config

### Summary
Optional skills in `~/.hermes/hermes-agent/optional-skills/` are not auto-discovered by `skills_list` — they exist on disk but are not loaded unless explicitly registered or copied to the active skills directory.

### Details
User asked to find the "financial statement skill". It wasn't in the `skills_list` output (58 skills). Manual filesystem search revealed it exists as `~/.hermes/hermes-agent/optional-skills/finance/3-statement-model/SKILL.md`. The skill is authored by Anthropic (adapted by Nous Research, Apache-2.0) and covers 3-statement financial modeling (Income Statement, Balance Sheet, Cash Flow) via openpyxl/Excel. To make it available, it needs to be copied or symlinked into the active skills directory.

### Suggested Action
Register the optional skill by copying it to the active skills path, or document in project memory that optional skills live in `~/.hermes/hermes-agent/optional-skills/` and require manual registration.

### Metadata
- Source: conversation
- Related Files: ~/.hermes/hermes-agent/optional-skills/finance/3-statement-model/SKILL.md
- Tags: skills, optional-skills, registration, finance, excel
- See Also:

---
