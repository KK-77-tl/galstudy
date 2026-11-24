"""Read-only migration and saved-story compatibility audit of the configured DB."""

import json
import sys
from pathlib import Path
from sqlalchemy import select, func

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from backend.db import (
    Session,
    Migration,
    Save,
    StoryRecord,
    ChatMessage,
    CharacterRecord,
    ImageJob,
)
from backend.story import DEMO, Story

with Session() as db:
    saves = db.scalars(select(Save)).all()
    invalid = []
    for saved in saves:
        record = db.get(StoryRecord, saved.story_id) if saved.story_id else None
        graph = Story.model_validate_json(record.graph) if record else DEMO
        if (saved.story_id and not record) or saved.node not in graph.nodes:
            invalid.append(saved.id)
    report = {
        "migrations": list(
            db.scalars(select(Migration.version).order_by(Migration.version))
        ),
        "legacy_demo_saves": sum(saved.story_id is None for saved in saves),
        "validated_saves": len(saves),
        "valid": not invalid,
        "processing_messages": db.scalar(
            select(func.count())
            .select_from(ChatMessage)
            .where(ChatMessage.status == "processing")
        ),
        "delivered_mock_characters": db.scalar(
            select(func.count())
            .select_from(CharacterRecord)
            .where(CharacterRecord.mode == "mock")
        ),
        "unfinished_image_jobs": db.scalar(
            select(func.count())
            .select_from(ImageJob)
            .where(
                ImageJob.status.in_(["queued", "submitting", "generating", "reviewing"])
            )
        ),
    }
    (ROOT / "docs/migration-result.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    print(json.dumps(report, indent=2))
    assert report["valid"], "Saved nodes are incompatible"
