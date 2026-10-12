"""
Pipeline knowledge base that persists corrections as actionable parameters.

Read from:  scripts/resource_processing_test/pipeline_knowledge.json
Written by: analyze_corrections.py (after every correction session)
Used by:   SmartPipeline, ImageClassifier, ScannedDocHandler at runtime

Auto-adjusts extraction behaviour based on accumulated user corrections.
"""

import json
import logging
from pathlib import Path
from threading import Lock

logger = logging.getLogger(__name__)

_KNOWLEDGE_PATH = (
    Path(__file__).parent.parent.parent
    / "scripts"
    / "resource_processing_test"
    / "pipeline_knowledge.json"
)
_lock = Lock()
_default_knowledge = None


def _get_defaults() -> dict:
    global _default_knowledge
    if _default_knowledge is None:
        _default_knowledge = {
            "version": 1,
            "last_updated": "2026-06-29T00:00:00",
            "total_corrections_processed": 0,
            "total_correction_files": 0,
            "heading_thresholds": {
                "pptx_h1_multiplier": 1.6,
                "pptx_h2_multiplier": 1.3,
                "pptx_h3_multiplier": 1.1,
            },
            "skip_images_md5": [],
            "decorative_patterns": [
                {"max_width": 100, "max_height": 100, "description": "small icons"},
                {"position": "corner", "max_size": 150, "description": "corner logos"},
            ],
            "heading_keywords": [
                "Introduction",
                "Overview",
                "Summary",
                "Conclusion",
                "Learning Outcomes",
                "Objectives",
                "Agenda",
                "Outline",
            ],
            "ppt_noise_patterns": ["slide number", "page \\d+", "confidential", "draft"],
            "bullet_chars_to_normalize": [],
            "ocr_config": {
                "clahe_clip_limit": 2.0,
                "denoise_strength": 10.0,
                "psm_printed": 3,
                "psm_handwritten": 6,
                "lang": "eng",
            },
            "correction_patterns": {
                "heading_level": {"count": 0, "by_format": {}},
                "mark_list": {"count": 0, "by_format": {}},
                "ignore_image": {"count": 0, "images": []},
                "ocr_correction": {"count": 0, "by_format": {}},
            },
            "performance": {
                "avg_processing_time_ms": 0,
                "total_files_processed": 0,
                "avg_score": 1.0,
                "score_history": [],
            },
        }
    return dict(_default_knowledge)


def load_knowledge() -> dict:
    with _lock:
        if not _KNOWLEDGE_PATH.exists():
            return _get_defaults()
        try:
            with open(_KNOWLEDGE_PATH) as f:
                data = json.load(f)
            defaults = _get_defaults()
            for key in defaults:
                if key not in data:
                    data[key] = defaults[key]
            return data
        except (OSError, json.JSONDecodeError) as e:
            logger.warning(f"Failed to load pipeline knowledge: {e}")
            return _get_defaults()


def save_knowledge(data: dict):
    with _lock:
        _KNOWLEDGE_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(_KNOWLEDGE_PATH, "w") as f:
            json.dump(data, f, indent=2)


class PipelineKnowledge:
    """Thread-safe interface to the knowledge base."""

    def __init__(self):
        self._data = load_knowledge()

    def reload(self):
        self._data = load_knowledge()

    @property
    def heading_thresholds(self) -> dict:
        return self._data.get("heading_thresholds", {})

    @property
    def skip_images_md5(self) -> list:
        return self._data.get("skip_images_md5", [])

    @property
    def decorative_patterns(self) -> list:
        return self._data.get("decorative_patterns", [])

    @property
    def heading_keywords(self) -> list:
        return self._data.get("heading_keywords", [])

    @property
    def ppt_noise_patterns(self) -> list:
        return self._data.get("ppt_noise_patterns", [])

    @property
    def bullet_chars_to_normalize(self) -> list:
        return self._data.get("bullet_chars_to_normalize", [])

    @property
    def ocr_config(self) -> dict:
        return self._data.get("ocr_config", {})

    @property
    def performance(self) -> dict:
        return self._data.get("performance", {})

    def get_pptx_h1_threshold(self, median_size: float) -> float:
        mult = self._data.get("heading_thresholds", {}).get("pptx_h1_multiplier", 1.6)
        return max(median_size * mult, 28.0)

    def get_pptx_h2_threshold(self, median_size: float) -> float:
        mult = self._data.get("heading_thresholds", {}).get("pptx_h2_multiplier", 1.3)
        return max(median_size * mult, 22.0)

    def get_pptx_h3_threshold(self, median_size: float) -> float:
        mult = self._data.get("heading_thresholds", {}).get("pptx_h3_multiplier", 1.1)
        return max(median_size * mult, 16.0)

    def should_skip_image(self, md5_hash: str) -> bool:
        return md5_hash in self._data.get("skip_images_md5", [])

    def record_performance(self, score: float, processing_time_ms: int):
        perf = self._data.setdefault("performance", {})
        perf["total_files_processed"] = perf.get("total_files_processed", 0) + 1
        total = perf["total_files_processed"]
        prev_avg = perf.get("avg_score", 1.0)
        perf["avg_score"] = ((prev_avg * (total - 1)) + score) / total
        prev_time = perf.get("avg_processing_time_ms", 0)
        perf["avg_processing_time_ms"] = int(
            ((prev_time * (total - 1)) + processing_time_ms) / total
        )
        history = perf.setdefault("score_history", [])
        history.append({"score": score, "at": __import__("datetime").datetime.utcnow().isoformat()})
        if len(history) > 100:
            perf["score_history"] = history[-100:]
        save_knowledge(self._data)

    def summary(self) -> str:
        data = self._data
        perf = data.get("performance", {})
        cp = data.get("correction_patterns", {})
        heading_count = cp.get("heading_level", {}).get("count", 0)
        total_corrections = sum(v.get("count", 0) for v in cp.values() if isinstance(v, dict))
        lines = [
            f"  Knowledge base: {_KNOWLEDGE_PATH.name}",
            f"  Corrections applied: {total_corrections}",
            f"  Heading corrections: {heading_count}",
            f"  Skipped image hashes: {len(data.get('skip_images_md5', []))}",
            f"  Files processed: {perf.get('total_files_processed', 0)}",
            f"  Average score: {perf.get('avg_score', 1.0):.4f}",
        ]
        return "\n".join(lines)
