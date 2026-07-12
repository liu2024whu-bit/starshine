from pathlib import Path

from starshine_geo.io import read_json, write_json
from starshine_geo.workflow import run_workflow

root = Path(__file__).resolve().parent
result = run_workflow(
    read_json(root / "workflow.json"),
    {
        "zones": read_json(root / "data" / "zones.geojson"),
        "sites": read_json(root / "data" / "sites.geojson"),
    },
)
output = write_json(result["zone_summary"], root / "output" / "zone_summary.geojson")
print(f"Wrote {output}")
