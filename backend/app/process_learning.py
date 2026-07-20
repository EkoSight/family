"""Process-learning module (early Phase 4).

Analyses the append-only event log for repeated task/event bundles and surfaces
process *candidates* as recommendations. It never creates a process on its own
— the CEO approves a candidate, which then becomes a ProcessDefinition.
"""
from __future__ import annotations

from collections import Counter, defaultdict

from sqlalchemy.orm import Session

from . import models


def detect(db: Session, min_frequency: int = 2) -> list[dict]:
    events = db.query(models.Event).order_by(models.Event.timestamp.asc()).all()

    # Group event types per project to find recurring sequences.
    by_project: dict[str, list[str]] = defaultdict(list)
    for e in events:
        key = e.project or "(unassigned)"
        by_project[key].append(e.event_type)

    # Count repeated event types overall as a simple repetition signal.
    type_counts = Counter(e.event_type for e in events)

    candidates: list[dict] = []
    for project, seq in by_project.items():
        if len(seq) < min_frequency:
            continue
        # collapse consecutive duplicates into a readable path
        path = []
        for ev in seq:
            if not path or path[-1] != ev:
                path.append(ev)
        frequency = len(seq)
        if frequency >= min_frequency and len(path) >= 2:
            candidates.append({
                "process_candidate": f"{project} workflow",
                "project": project,
                "event_sequence": " → ".join(path[:8]),
                "frequency": frequency,
                "recommendation":
                    f"Detected a repeated sequence in '{project}' "
                    f"({frequency} events). Consider standardising it.",
            })

    # Repeated task bundles: same task titles created many times.
    repeated = [{"process_candidate": t, "frequency": c,
                 "recommendation": f"'{t}' recurs {c} times — candidate for a "
                                   f"reusable workflow block."}
                for t, c in type_counts.items() if c >= min_frequency
                and t == "task_created"]
    candidates.extend(repeated)
    return candidates
