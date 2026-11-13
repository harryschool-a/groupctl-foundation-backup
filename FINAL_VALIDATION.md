# v1.0 validation checklist

Run each command separately:

```powershell
python -m unittest discover -s tests -v
python groupctl.py validate
python groupctl.py status
python groupctl.py dashboard --output .group/local/dashboard.html
python scripts/run_three_member_demo.py --auto-confirm-final
```

For repositories with a configured remote, also test:

```powershell
python groupctl.py sync --remote origin
```

The dashboard is a local report and does not modify collaboration history. The audit command may intentionally return a non-zero attention status when historical changes lack independent reviews.
