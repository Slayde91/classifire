---
name: quantifire
description: Operate and administer the QUANTIFIRE passive-fire estimating and technical decision-support system through its controlled CLI and API.
---

# QUANTIFIRE OpenClaw skill

QUANTIFIRE is an estimating system produced and developed by Ceasefire PFP.

Use QUANTIFIRE's typed API or CLI for all canonical reads and writes. Do not treat agent memory, chat history or Mission Control task text as the estimate database.

## Mandatory boundaries

- Physical modelling precedes technical selection.
- Technical selection precedes commercial pricing.
- Package 15 controls technical applicability.
- Package 14 controls commercial pricing.
- AI-extracted technical information remains Draft until authorised approval.
- Agents may not self-approve library changes or estimates.
- Released estimates and library releases are immutable.
- A cost allowance is not technical approval.
- Do not expose confidential pricing or technical source records.

## Local commands

```bash
quantifire doctor
quantifire start
quantifire worker
```

Use the Mission Control adapter only for architecture, task, review, incident and release coordination. Canonical project, library and estimate state remains within QUANTIFIRE.
