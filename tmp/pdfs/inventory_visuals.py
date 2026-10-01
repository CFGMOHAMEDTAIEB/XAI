from pathlib import Path
import csv

from PIL import Image, ImageDraw, ImageOps


REPORT = Path(r"C:\Users\ss\Desktop\XAI\last-Pro-Report")
OUT = Path(r"C:\Users\ss\Desktop\XAI\XAI\tmp\pdfs\visual-inventory")
OUT.mkdir(parents=True, exist_ok=True)

roots = [("iput", REPORT / "iput"), ("tools", REPORT / "images" / "tools")]
records = []
renderable = []

for group, root in roots:
    for path in sorted(root.rglob("*"), key=lambda p: str(p).lower()):
        if not path.is_file():
            continue
        width = height = mode = ""
        try:
            with Image.open(path) as source:
                width, height = source.size
                mode = source.mode
            renderable.append((group, path, width, height))
        except Exception:
            pass
        records.append(
            {
                "group": group,
                "filename": path.name,
                "path": str(path),
                "extension": path.suffix.lower(),
                "bytes": path.stat().st_size,
                "width": width,
                "height": height,
                "mode": mode,
            }
        )

with (OUT / "metadata.csv").open("w", newline="", encoding="utf-8-sig") as stream:
    writer = csv.DictWriter(stream, fieldnames=records[0].keys())
    writer.writeheader()
    writer.writerows(records)

thumb = (620, 410)
label_height = 74
cols, rows = 2, 2
for start in range(0, len(renderable), cols * rows):
    batch = renderable[start : start + cols * rows]
    sheet = Image.new("RGB", (cols * thumb[0], rows * (thumb[1] + label_height)), "white")
    draw = ImageDraw.Draw(sheet)
    for index, (group, path, width, height) in enumerate(batch):
        with Image.open(path) as source:
            image = ImageOps.exif_transpose(source).convert("RGB")
            image.thumbnail((thumb[0] - 20, thumb[1] - 20))
        x0 = (index % cols) * thumb[0]
        y0 = (index // cols) * (thumb[1] + label_height)
        x = x0 + (thumb[0] - image.width) // 2
        y = y0 + (thumb[1] - image.height) // 2
        sheet.paste(image, (x, y))
        draw.rectangle((x0, y0, x0 + thumb[0] - 1, y0 + thumb[1] + label_height - 1), outline="#b7b7b7")
        draw.text((x0 + 10, y0 + thumb[1] + 8), f"[{group}] {path.name}", fill="black")
        draw.text((x0 + 10, y0 + thumb[1] + 32), f"{width} x {height} px", fill="#333333")
    sheet.save(OUT / f"contact-{start + 1:03d}-{start + len(batch):03d}.jpg", quality=88, optimize=True)

print(f"records={len(records)} images={len(renderable)} contacts={(len(renderable) + 3) // 4}")
