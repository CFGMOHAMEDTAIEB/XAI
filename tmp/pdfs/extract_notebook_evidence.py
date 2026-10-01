from pathlib import Path
import base64
import hashlib
import json
import re


NOTEBOOKS = {
    "iput": Path(r"C:\Users\ss\Desktop\XAI\last-Pro-Report\iput\XAI_Compress_Model_Analysis.ipynb"),
    "project": Path(r"C:\Users\ss\Desktop\XAI\XAI\notebooks\XAI_Compress_Model_Analysis.ipynb"),
}
OUT = Path(r"C:\Users\ss\Desktop\XAI\XAI\tmp\pdfs\notebook-evidence")
OUT.mkdir(parents=True, exist_ok=True)


def join_source(value):
    return "".join(value) if isinstance(value, list) else str(value or "")


for name, path in NOTEBOOKS.items():
    notebook = json.loads(path.read_text(encoding="utf-8"))
    target = OUT / name
    target.mkdir(exist_ok=True)
    report = [f"# {path}", ""]
    image_index = 0
    for cell_index, cell in enumerate(notebook.get("cells", [])):
        source = join_source(cell.get("source", []))
        report.extend([f"## Cell {cell_index} ({cell.get('cell_type')})", "", source, ""])
        for output_index, output in enumerate(cell.get("outputs", [])):
            report.append(f"### Output {output_index} ({output.get('output_type')})")
            if "text" in output:
                report.extend(["", join_source(output["text"]), ""])
            data = output.get("data", {})
            for mime, value in data.items():
                if mime in ("image/png", "image/jpeg"):
                    image_index += 1
                    extension = ".png" if mime == "image/png" else ".jpg"
                    payload = base64.b64decode(join_source(value))
                    digest = hashlib.sha256(payload).hexdigest()[:12]
                    image_path = target / f"cell-{cell_index:02d}-output-{output_index:02d}-{image_index:02d}-{digest}{extension}"
                    image_path.write_bytes(payload)
                    report.append(f"Embedded image: {image_path.name} ({len(payload)} bytes)")
                elif mime in ("text/plain", "text/markdown", "text/html"):
                    text = join_source(value)
                    if mime == "text/html":
                        text = re.sub(r"<[^>]+>", " ", text)
                    report.extend([f"", f"[{mime}]", text, ""])
            if output.get("ename") or output.get("evalue"):
                report.append(f"ERROR {output.get('ename')}: {output.get('evalue')}")
        report.append("")
    (target / "inspection.md").write_text("\n".join(report), encoding="utf-8")
    print(name, "cells", len(notebook.get("cells", [])), "images", image_index)
