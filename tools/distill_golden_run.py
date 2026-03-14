from __future__ import annotations

# pyright: reportAny=false, reportUnusedCallResult=false

import argparse
import json
import sys
from pathlib import Path

if __package__ is None or __package__ == "":
    project_root = Path(__file__).resolve().parents[1]
    root_text = str(project_root)
    if root_text not in sys.path:
        sys.path.insert(0, root_text)

from core.golden_run_distillation import GoldenRunDistillationError, GoldenRunDistiller
from core.model_trace_store import ModelTraceContext, ModelTraceStore


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Distill one successful golden-run trace into reviewable YAML drafts.")
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--target-label", required=True)
    parser.add_argument("--attempt-number", required=True, type=int)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--plugin-name")
    parser.add_argument("--display-name")
    parser.add_argument("--category", default="AI Drafts")
    parser.add_argument("--traces-root", type=Path)
    parser.add_argument("--use-llm-refiner", action="store_true", help="Run LLM-based parametrization refinement after base distillation")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    context = ModelTraceContext(
        task_id=args.task_id,
        run_id=args.run_id,
        target_label=args.target_label,
        attempt_number=args.attempt_number,
    )
    distiller = GoldenRunDistiller(trace_store=ModelTraceStore(root_dir=args.traces_root) if args.traces_root else None)
    try:
        draft = distiller.distill(
            context=context,
            output_dir=args.output_dir,
            plugin_name=args.plugin_name,
            display_name=args.display_name,
            category=args.category,
        )
    except GoldenRunDistillationError as exc:
        print(json.dumps(exc.to_dict(), ensure_ascii=False, sort_keys=True))
        return 1

    if args.use_llm_refiner:
        records = distiller._trace_store.read_records(context)
        draft = distiller.refine_draft(draft, records)

    print(
        json.dumps(
            {
                "ok": True,
                "manifest_path": str(draft.manifest_path),
                "script_path": str(draft.script_path),
                "plugin_name": draft.manifest.name,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
