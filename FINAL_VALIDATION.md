# v1.1 Validation Checklist

Run the following separately from the repository root:

```powershell
python groupctl.py --version
python -m unittest discover -s tests -v
python groupctl.py validate
python groupctl.py status
python groupctl.py audit
python groupctl.py dashboard --output .group/local/dashboard.html
```

The local automated suite validates the v1.1 runtime against a fake OpenAI-compatible HTTP endpoint. It covers concurrent agent requests, JSON response validation, task ownership, agent attribution, reviewer behavior, code-proposal patch integrity, human-gated patch application, and publishing.

The three-member regression simulation can be run with:

```powershell
python scripts/run_three_member_demo.py --auto-confirm-final
```

The demo creates temporary local clones and a temporary bare Git remote. It does not contact GitHub and does not prove real multi-user permissions or live model reasoning.

For a live model run, see `QUICKSTART_V1.1_LIVE_AGENTS.md`. A compatible local or hosted model endpoint must be available. The automated tests do not require a paid provider account.

The dashboard is a local report and does not modify collaboration history. The audit command may intentionally return a non-zero attention status when historical changes lack independent member or distinct-agent reviews. A distinct AI-agent review under the same `person_id` is not equivalent to an independent human review.
