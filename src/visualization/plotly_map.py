from __future__ import annotations

import json
from html import escape
from pathlib import Path

from plotly.offline import get_plotlyjs

from src.models import DISCOURSE_TYPES, UmapCoordinate
from src.storage.files import ensure_directory


def _hover_html(item: UmapCoordinate) -> str:
    lines = []
    if item.metadata.get("country"):
        lines.append(f"Country: {escape(item.metadata['country'])}")
    if item.metadata.get("location"):
        lines.append(f"Location: {escape(item.metadata['location'])}")
    if item.metadata.get("medium"):
        lines.append(f"Medium: {escape(item.metadata['medium'])}")
    if item.metadata.get("collection"):
        lines.append(f"Collection: {escape(item.metadata['collection'])}")
    if item.extracted_fields:
        field_lines = [
            f"{escape(field['field'])}: {escape(field['value'])}" for field in item.extracted_fields
        ]
        lines.append("Fields: " + " | ".join(field_lines))
    return "<br>".join(lines)


def render_exhibit_map(coordinates: list[UmapCoordinate], output_path: Path) -> None:
    ensure_directory(output_path.parent)
    rows = [
        {
            "exhibit_id": item.exhibit_id,
            "title": item.title or item.exhibit_id,
            "discourse": item.discourse,
            "view": item.view,
            "x": item.x,
            "y": item.y,
            "hover": _hover_html(item),
            "field_count": len(item.extracted_fields),
        }
        for item in coordinates
    ]
    views = ["technical", "category", "exhibition", "perception", "overall"]
    discourses = list(DISCOURSE_TYPES)
    plotly_js = get_plotlyjs()
    payload = json.dumps(rows, ensure_ascii=False)
    view_payload = json.dumps(views)
    discourse_payload = json.dumps(discourses)
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <title>Exhibit Semantic Map</title>
  <style>
    body {{
      font-family: "Segoe UI", sans-serif;
      margin: 0;
      background: linear-gradient(180deg, #f5efe6 0%, #ffffff 60%);
      color: #1f2933;
    }}
    .wrap {{
      max-width: 1280px;
      margin: 0 auto;
      padding: 24px;
    }}
    .toolbar {{
      display: flex;
      gap: 12px;
      flex-wrap: wrap;
      align-items: center;
      margin-bottom: 16px;
    }}
    select {{
      padding: 8px 12px;
      border-radius: 999px;
      border: 1px solid #cbd5e1;
      background: white;
    }}
    #plot {{
      width: 100%;
      height: 78vh;
      border-radius: 24px;
      background: rgba(255,255,255,0.8);
      box-shadow: 0 16px 40px rgba(15, 23, 42, 0.08);
    }}
  </style>
</head>
<body>
  <div class="wrap">
    <h1>Multi-Discourse Multi-View Exhibit Map</h1>
    <div class="toolbar">
      <label for="viewSelect">View</label>
      <select id="viewSelect"></select>
      <label for="discourseSelect">Discourse</label>
      <select id="discourseSelect"></select>
    </div>
    <div id="plot"></div>
  </div>
  <script>{plotly_js}</script>
  <script>
    const rows = {payload};
    const views = {view_payload};
    const discourses = {discourse_payload};
    const viewSelect = document.getElementById("viewSelect");
    const discourseSelect = document.getElementById("discourseSelect");

    function fillSelect(select, values) {{
      values.forEach((value) => {{
        const option = document.createElement("option");
        option.value = value;
        option.textContent = value.replace(/_/g, " ");
        select.appendChild(option);
      }});
    }}

    fillSelect(viewSelect, views);
    fillSelect(discourseSelect, discourses);

    function currentRows() {{
      return rows.filter((row) => row.view === viewSelect.value && row.discourse === discourseSelect.value);
    }}

    function render() {{
      const active = currentRows();
      const trace = {{
        x: active.map((row) => row.x),
        y: active.map((row) => row.y),
        text: active.map((row) => row.title),
        customdata: active.map((row) => [row.title, row.hover]),
        mode: "markers+text",
        type: "scattergl",
        textposition: "top center",
        marker: {{
          size: active.map((row) => Math.max(10, 8 + row.field_count * 1.5)),
          color: active.map((row) => row.field_count),
          colorscale: "Viridis",
          opacity: 0.85,
          line: {{ width: 1, color: "#102a43" }}
        }},
        hovertemplate: "<b>%{{customdata[0]}}</b><br>%{{customdata[1]}}<extra></extra>"
      }};

      const layout = {{
        title: `${{viewSelect.value.replace(/_/g, " ")}} | ${{discourseSelect.value.replace(/_/g, " ")}}`,
        paper_bgcolor: "rgba(0,0,0,0)",
        plot_bgcolor: "rgba(255,255,255,0.7)",
        margin: {{ t: 60, r: 24, b: 40, l: 48 }},
        xaxis: {{ title: "UMAP-1", zeroline: false }},
        yaxis: {{ title: "UMAP-2", zeroline: false }},
      }};

      Plotly.react("plot", [trace], layout, {{ responsive: true }});
    }}

    viewSelect.value = views[0];
    discourseSelect.value = discourses[0];
    viewSelect.addEventListener("change", render);
    discourseSelect.addEventListener("change", render);
    render();
  </script>
</body>
</html>
"""
    output_path.write_text(html, encoding="utf-8")
