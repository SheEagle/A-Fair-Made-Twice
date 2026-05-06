from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from src.models import DifyWorkflowSpec


def parse_dify_workflow(path: Path) -> DifyWorkflowSpec:
    if not path.exists():
        return DifyWorkflowSpec()

    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    graph: dict[str, Any] = payload.get("workflow", {}).get("graph", {})
    nodes = graph.get("nodes", [])

    query_prompt = None
    extraction_prompt = None
    top_k = None

    for node in nodes:
        data = node.get("data", {})
        node_type = data.get("type")
        title = str(data.get("title", "")).strip().lower()
        if node_type == "knowledge-retrieval":
            top_k = data.get("multiple_retrieval_config", {}).get("top_k")
        if node_type == "llm" and "query" in title:
            prompt_template = data.get("prompt_template", [])
            if prompt_template:
                query_prompt = prompt_template[0].get("text")
        if node_type == "llm" and "extraction" in title:
            prompt_template = data.get("prompt_template", [])
            if prompt_template:
                extraction_prompt = prompt_template[0].get("text")

    return DifyWorkflowSpec(
        app_name=payload.get("app", {}).get("name"),
        query_prompt=query_prompt,
        extraction_prompt=extraction_prompt,
        retrieval_top_k=top_k,
    )
