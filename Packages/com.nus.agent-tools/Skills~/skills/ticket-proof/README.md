# ticket-proof: setup

Posts proof of work to Azure DevOps tickets. Needs Python 3.9+, Git, the Azure CLI (`az login` once per machine), and
Pillow only for outlines and crops (`pip install pillow`).

## Which board

Put `.claude/ticket-board.json` in the project and commit it:

```json
{
  "organization": "nusit-aat-rt",
  "project": "Infection Control VR AI (Nursing)"
}
```

Without the file, the board is the Azure DevOps project of the repository's `origin` remote.

Optional fields:

| Field | Use |
|---|---|
| `team` | Take sprints from this team's settings instead of every dated iteration in the project. |
| `areaPath` | Only list tickets under this area, when several products share one project. |
| `excludeTypes` | Work item types `tickets` leaves out (default `["Epic", "Feature"]`). |
| `azureSubscription` | The Azure CLI subscription whose sign-in reaches the board, when a person has several. |
| `capturesFolder` | Where captures wait to post (default `Artifacts/TicketProof`; add it to `.gitignore`). |

Moving the project to another board means editing this file; nothing else changes.

Check it with `python <skill folder>/scripts/ticket_proof.py doctor`.

## Tests

`python -m pytest scripts/test_ticket_proof.py` (no network).
