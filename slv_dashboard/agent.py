"""Future: draft the weekly brief and monthly pitch through the Anthropic API.

Not built yet. For the MVP the agent is Claude Code, running the skills in
.claude/skills/ (weekly-brief, monthly-pitch), which use the same prompts in
prompts/. That keeps the agent's instructions in one place, so this module
only has to add the API plumbing when the club wants briefs drafted
unattended (e.g. by the refresh-data workflow).

The plan when it is built:
- Set ANTHROPIC_API_KEY in .env locally, or as a GitHub Actions secret.
- Send prompts/weekly_brief.md as the system prompt, with snapshot.json, brief.md and the top rows of
  news.csv as the user message. Give the model a web-search tool so it can verify news, as the skill does.
- Parse the returned AGENT blocks back into brief.md, then call export.export(html_only=True).
- Use the latest Claude model, and pin the model id in config.
"""

import os

from slv_dashboard.config import ROOT

PROMPTS_DIR = ROOT / "prompts"


def api_key() -> str:
    return os.getenv("ANTHROPIC_API_KEY", "")


def draft_brief(report_dir) -> None:
    if not api_key():
        raise SystemExit("ANTHROPIC_API_KEY is not set. For now, run the weekly-brief skill in Claude Code "
                         "(see README, 'Agent').")
    raise NotImplementedError("API drafting is planned; see the module docstring. Use the Claude Code skill meanwhile.")
