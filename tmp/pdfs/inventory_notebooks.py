from pathlib import Path
import csv
import hashlib
import json


ROOTS = [
    Path(r"C:\Users\ss\Desktop\XAI\last-Pro-Report"),
    Path(r"C:\Users\ss\Desktop\XAI\XAI"),
]
OUT = Path(r"C:\Users\ss\Desktop\XAI\XAI\tmp\pdfs\visual-inventory")
OUT.mkdir(parents=True, exist_ok=True)

records = []
for root in ROOTS:
    for path in sorted(root.rglob("*.ipynb"), key=lambda p: str(p).lower()):
        raw = path.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        try:
            notebook = json.loads(raw.decode("utf-8"))
            cells = notebook.get("cells", [])
            markdown = [cell for cell in cells if cell.get("cell_type") == "markdown"]
            code = [cell for cell in cells if cell.get("cell_type") == "code"]
            outputs = [output for cell in code for output in cell.get("outputs", [])]
            image_outputs = []
            for cell_index, cell in enumerate(cells):
                for output_index, output in enumerate(cell.get("outputs", [])):
                    data = output.get("data", {})
                    for mime in ("image/png", "image/jpeg", "image/svg+xml"):
                        if mime in data:
                            image_outputs.append(f"{cell_index}:{output_index}:{mime}")
            headings = []
            for cell in markdown:
                for line in "".join(cell.get("source", [])).splitlines():
                    if line.lstrip().startswith("#"):
                        headings.append(line.strip())
            records.append(
                {
                    "path": str(path),
                    "bytes": len(raw),
                    "sha256": digest,
                    "cells": len(cells),
                    "markdown_cells": len(markdown),
                    "code_cells": len(code),
                    "outputs": len(outputs),
                    "image_outputs": len(image_outputs),
                    "image_locations": ";".join(image_outputs),
                    "headings": " | ".join(headings[:20]),
                    "error": "",
                }
            )
        except Exception as exc:
            records.append(
                {
                    "path": str(path),
                    "bytes": len(raw),
                    "sha256": digest,
                    "cells": "",
                    "markdown_cells": "",
                    "code_cells": "",
                    "outputs": "",
                    "image_outputs": "",
                    "image_locations": "",
                    "headings": "",
                    "error": repr(exc),
                }
            )

with (OUT / "notebooks.csv").open("w", newline="", encoding="utf-8-sig") as stream:
    writer = csv.DictWriter(stream, fieldnames=records[0].keys())
    writer.writeheader()
    writer.writerows(records)

groups = {}
for record in records:
    groups.setdefault(record["sha256"], []).append(record)

summary = {
    "total_files": len(records),
    "unique_hashes": len(groups),
    "groups": [
        {
            "sha256": digest,
            "copies": len(items),
            "representative": items[0]["path"],
            "cells": items[0]["cells"],
            "outputs": items[0]["outputs"],
            "image_outputs": items[0]["image_outputs"],
        }
        for digest, items in sorted(groups.items(), key=lambda item: (-len(item[1]), item[0]))
    ],
}
(OUT / "notebooks-summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")

print(f"notebooks={len(records)} unique_hashes={len(groups)}")
for item in summary["groups"][:30]:
    print(item)
