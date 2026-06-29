"""One-command evaluation pipeline.

Usage:
    python -m app.evaluation.run_full_eval

Runs the full evaluation dataset (48 cases), controlled experiments,
and outputs a structured report.
"""

import asyncio
import json
import sys
from datetime import datetime


async def main():
    from app.evaluation.dataset import generate_dataset, dataset_summary
    from app.evaluation.runner import run_evaluation, compute_metrics
    from app.evaluation.experiments import run_all_experiments

    print("=" * 60)
    print("Incident Diagnosis Agent - Full Evaluation Pipeline")
    print("=" * 60)

    # 1. Dataset summary
    cases = generate_dataset()
    summary = dataset_summary(cases)
    print(f"\n[1/3] Dataset: {summary['total_cases']} cases, "
          f"{summary['faults_covered']} faults, "
          f"{len(summary['by_category'])} categories")
    print(f"  Variants: {summary['by_variant']}")

    # 2. Run evaluation
    print(f"\n[2/3] Running evaluation on {len(cases)} cases...")
    results = await run_evaluation(use_llm=False)
    metrics = compute_metrics(results)

    rb = metrics.get("rule_based", {})
    print(f"  Rule-Based Top-1 Accuracy: {rb.get('top1_accuracy', 0):.1%}")
    print(f"  Rule-Based Top-3 Recall:   {rb.get('top3_recall', 0):.1%}")
    print(f"  Avg Latency:               {rb.get('avg_latency_ms', 0):.0f}ms")
    print(f"  Forbidden Violations:      {rb.get('forbidden_violation_rate', 0):.1%}")
    print(f"  Inconclusive Rate:         {rb.get('inconclusive_rate', 0):.1%}")

    # 3. Controlled experiments
    print(f"\n[3/3] Running 4 controlled experiments...")
    experiments = await run_all_experiments()
    for exp in experiments:
        print(f"  [{exp.experiment_name}]")
        print(f"    {exp.conclusion}")

    # Save full report
    report = {
        "timestamp": datetime.utcnow().isoformat(),
        "dataset": summary,
        "metrics": metrics,
        "experiments": [
            {
                "name": e.experiment_name,
                "variant_a": e.variant_a_name,
                "variant_b": e.variant_b_name,
                "a_top1": e.variant_a_top1,
                "b_top1": e.variant_b_top1,
                "a_top3": e.variant_a_top3,
                "b_top3": e.variant_b_top3,
                "conclusion": e.conclusion,
            }
            for e in experiments
        ],
    }

    output_path = "eval_report.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    print(f"\nReport saved to: {output_path}")
    print("=" * 60)

    return report


if __name__ == "__main__":
    asyncio.run(main())
