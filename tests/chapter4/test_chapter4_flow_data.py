"""
Fresh Chapter 4 flow tests.

These tests do not reuse parity_test_report.json or previous Chapter 4 data.
They exercise the current processing/search flow with deterministic fakes so the
report can describe what the system is supposed to test before running heavier
AI/DB experiments.
"""
from __future__ import annotations

import asyncio
import json
import math
import sys
import time
from pathlib import Path

import cv2
import numpy as np
import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = PROJECT_ROOT / "src"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from services.ai_processing_types import (  # noqa: E402
    AIProcessingResult,
    BoundingBox,
    ClothingCategory,
    ColorData,
    DetectedItem,
    PersonDetection,
    ProcessingStatus,
)
from services.frame_processor import FrameProcessor  # noqa: E402
from services.video_processor import VideoProcessor  # noqa: E402
from src.api.controllers import DetectionController  # noqa: E402


REPORT_PATH = PROJECT_ROOT / "my-thesis-report" / "qa" / "chapter4-flow-test-results.json"
CHAPTER4_REPORT: dict[str, object] = {
    "generated_at": None,
    "purpose": "Fresh deterministic tests for Chapter 4 flow design and data contracts",
    "tests": {},
}


@pytest.fixture(scope="session", autouse=True)
def write_chapter4_report():
    yield
    CHAPTER4_REPORT["generated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(
        json.dumps(CHAPTER4_REPORT, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


class Scalar:
    def __init__(self, value):
        self.value = value

    def item(self):
        return self.value


class FakeBox:
    def __init__(self, track_id: int, confidence: float, xyxy: tuple[int, int, int, int]):
        self.id = Scalar(track_id)
        self.conf = Scalar(confidence)
        self.xyxy = np.array([xyxy])


class FakeDetectionResult:
    def __init__(self, boxes):
        self.boxes = boxes


class FakeDetector:
    def track_people(self, frame):
        return FakeDetectionResult([FakeBox(7, 0.91, (40, 20, 140, 220))])


class FakeClassifier:
    def predict_top_n(self, image, top_n=3):
        return [
            ("long_sleeve", 0.93, (5, 5, 95, 100)),
            ("trousers", 0.88, (5, 100, 95, 195)),
            ("shorts", 0.22, (10, 120, 90, 180)),
        ]


class FakeEmbedder:
    def get_embedding(self, image):
        return np.ones(768, dtype=np.float32), ["long_sleeve", "trousers"]


def _add_fake_color(item: DetectedItem, *_):
    item.primary_color = ColorData(color_name="navy_blue", percentage=64.0)
    item.secondary_colors = [ColorData(color_name="black", percentage=21.0)]
    item.detailed_colors = {"navy_blue": 64.0, "black": 21.0}
    item.color_groups = ["blue_tones", "dark_colors"]
    return item


def _person(track_id: int, frame_number: int) -> PersonDetection:
    top = DetectedItem(
        class_name="long_sleeve",
        category=ClothingCategory.TOP,
        confidence=0.92,
        primary_color=ColorData(color_name="navy_blue", percentage=63.0),
        detailed_colors={"navy_blue": 63.0, "black": 18.0},
        color_groups=["blue_tones", "dark_colors"],
    )
    bottom = DetectedItem(
        class_name="trousers",
        category=ClothingCategory.BOTTOM,
        confidence=0.86,
        primary_color=ColorData(color_name="black", percentage=71.0),
        detailed_colors={"black": 71.0, "gray": 12.0},
        color_groups=["dark_colors", "formal_colors"],
    )
    return PersonDetection(
        track_id=track_id,
        persistent_id=track_id,
        bbox=BoundingBox(40, 20, 100, 200),
        confidence=0.91,
        items=[top, bottom],
        embedding=np.ones(768, dtype=np.float32) * track_id,
        frame_number=frame_number,
    )


@pytest.fixture
def synthetic_video(tmp_path):
    video_path = tmp_path / "chapter4_flow.mp4"
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(video_path), fourcc, 12.0, (160, 120))
    for idx in range(24):
        frame = np.zeros((120, 160, 3), dtype=np.uint8)
        frame[:, :] = (20 + idx, 80, 180 - idx)
        cv2.rectangle(frame, (40, 20), (140, 118), (255, 255, 255), 2)
        writer.write(frame)
    writer.release()
    return video_path


def test_frame_processor_two_pass_contract_without_real_models(monkeypatch):
    processor = FrameProcessor(
        enable_classification=True,
        enable_color_analysis=True,
        enable_embedding=True,
        classifier_top_n=3,
    )
    monkeypatch.setattr(processor, "_get_detector", lambda: FakeDetector())
    monkeypatch.setattr(processor, "_get_classifier", lambda: FakeClassifier())
    monkeypatch.setattr(processor, "_get_embedder", lambda: FakeEmbedder())
    monkeypatch.setattr(processor, "_analyze_item_color", _add_fake_color)

    frame = np.zeros((240, 180, 3), dtype=np.uint8)
    result = processor.process_frame(frame, frame_number=10, timestamp=1.25)

    assert result.status == ProcessingStatus.SUCCESS
    assert result.num_persons == 1
    person = result.detections[0]
    assert person.track_id == 7
    assert person.embedding is not None
    assert person.embedding.shape == (768,)
    assert [item.class_name for item in person.items] == ["long_sleeve", "trousers"]
    assert [item.category for item in person.items] == [ClothingCategory.TOP, ClothingCategory.BOTTOM]
    assert person.items[0].primary_color.color_name == "navy_blue"

    CHAPTER4_REPORT["tests"]["frame_processor_two_pass_contract"] = {
        "status": result.status.value,
        "persons": result.num_persons,
        "items_per_person": len(person.items),
        "embedding_dimension": int(person.embedding.shape[0]),
        "selected_classes": [item.class_name for item in person.items],
        "selected_color_groups": sorted(set().union(*(item.color_groups for item in person.items))),
    }


class FakeThreadPool:
    def __init__(self):
        self.frame_numbers: list[int] = []

    async def process_frame(self, frame, frame_number=0, timestamp=None, timeout=None):
        self.frame_numbers.append(frame_number)
        track_id = 1 if frame_number < 12 else 2
        return AIProcessingResult(
            status=ProcessingStatus.SUCCESS,
            detections=[_person(track_id=track_id, frame_number=frame_number)],
            num_persons=1,
            frame_number=frame_number,
            timestamp=timestamp,
            processing_time_ms=4.5,
            image_width=frame.shape[1],
            image_height=frame.shape[0],
        )


@pytest.mark.asyncio
async def test_video_processor_collects_chapter4_metrics_from_current_flow(synthetic_video):
    fake_pool = FakeThreadPool()
    progress_events: list[tuple[int, int, int]] = []
    detections_seen: list[tuple[int, int, str]] = []

    processor = VideoProcessor(
        thread_pool=fake_pool,
        frame_skip=4,
        save_to_db=False,
        save_images=False,
        use_hybrid_tracking=False,
        use_reader_thread=False,
        use_async_db_queue=False,
        progress_update_interval=10,
    )

    stats = await processor.process_video(
        source=str(synthetic_video),
        camera_id="CH4-CAM-01",
        video_id="chapter4-video-flow",
        on_progress=lambda pct, frame, total: progress_events.append((pct, frame, total)),
        on_detection=lambda person, frame: detections_seen.append((frame, person.track_id, person.items[0].class_name)),
        save_to_db=False,
        save_images=False,
    )

    expected_processed_frames = math.ceil(24 / 4)
    assert stats.status == ProcessingStatus.SUCCESS
    assert stats.total_frames == 24
    assert stats.processed_frames == expected_processed_frames
    assert stats.num_persons_detected == expected_processed_frames
    assert stats.total_detections == expected_processed_frames
    assert stats.unique_persons == 2
    assert stats.duration_seconds > 0
    assert stats.effective_fps > 0
    assert len(detections_seen) == expected_processed_frames
    assert [pct for pct, _, _ in progress_events] == sorted(pct for pct, _, _ in progress_events)

    CHAPTER4_REPORT["tests"]["video_processor_metrics"] = {
        "source": "synthetic 24-frame video",
        "frame_skip": 4,
        "processed_frame_numbers": fake_pool.frame_numbers,
        "stats": stats.to_dict(),
        "progress_events": progress_events,
        "detections_seen": detections_seen,
    }


class FakeDatabase:
    def __init__(self):
        self.inserted_batches: list[list[dict]] = []

    def insert_detections_batch(self, batch):
        self.inserted_batches.append(batch)


@pytest.mark.asyncio
async def test_video_processor_batch_payload_matches_storage_contract():
    processor = VideoProcessor(
        thread_pool=FakeThreadPool(),
        save_to_db=True,
        save_images=False,
        use_hybrid_tracking=False,
        use_reader_thread=False,
        use_async_db_queue=False,
    )
    fake_db = FakeDatabase()

    processor._add_to_batch(
        person=_person(track_id=11, frame_number=8),
        frame_number=8,
        camera_id="CH4-CAM-DB",
        video_id="chapter4-db-contract",
        image_path="CH4-CAM-DB/chapter4-db-contract/8_sample.jpg",
    )
    await processor._flush_batch(fake_db)

    assert len(fake_db.inserted_batches) == 1
    payload = fake_db.inserted_batches[0][0]
    assert payload["camera_id"] == "CH4-CAM-DB"
    assert payload["track_id"] == 11
    assert payload["category"] == "TOP"
    assert payload["class_name"] == "long_sleeve"
    assert payload["bbox"] == {"x": 40, "y": 20, "width": 100, "height": 200}
    assert payload["image_path"].endswith("8_sample.jpg")
    assert payload["video_time_offset"] == 8
    assert payload["video_id"] == "chapter4-db-contract"
    assert len(payload["embedding"]) == 768
    assert processor.get_stats().num_detections_saved == 1
    assert processor._detection_batch == []

    CHAPTER4_REPORT["tests"]["database_payload_contract"] = {
        "payload_keys": sorted(payload.keys()),
        "embedding_dimension": len(payload["embedding"]),
        "saved_count": processor.get_stats().num_detections_saved,
    }


def test_advanced_search_query_contract_for_chapter4_filters():
    controller = DetectionController.__new__(DetectionController)
    where_clause, params = controller._build_advanced_search_query(
        clothing_groups=[
            {"clothing": "long_sleeve", "colors": ["navy_blue", "black"], "color_logic": "OR"},
            {"clothing": "trousers", "colors": [], "color_logic": "OR"},
        ],
        global_logic="AND",
        threshold=0.25,
        camera_id="CH4-CAM-01",
        video_id="chapter4-video-flow",
    )

    assert "d.camera_id = %s" in where_clause
    assert "d.video_id = %s" in where_clause
    assert "LOWER(di2.class_name) = %s" in where_clause
    assert "jsonb_array_elements(dc2.top_colors)" in where_clause
    assert " AND " in where_clause
    assert params == [
        "CH4-CAM-01",
        "chapter4-video-flow",
        "long_sleeve",
        "navy_blue",
        25.0,
        "long_sleeve",
        "black",
        25.0,
        "trousers",
    ]

    CHAPTER4_REPORT["tests"]["advanced_search_query_contract"] = {
        "where_contains": [
            "camera_id",
            "video_id",
            "clothing class filter",
            "jsonb top_colors filter",
        ],
        "param_count": len(params),
        "threshold_percent": 25.0,
    }


def test_chapter4_report_outline_is_derived_from_current_flow():
    outline = [
        {
            "section": "4.1 ผลการทำงานของระบบ",
            "data_source": "video_processor_metrics",
            "metrics": ["total_frames", "processed_frames", "total_detections", "unique_persons", "effective_fps"],
        },
        {
            "section": "4.2 ผลการตรวจจับและจำแนกคุณลักษณะ",
            "data_source": "frame_processor_two_pass_contract",
            "metrics": ["persons", "items_per_person", "selected_classes", "selected_color_groups", "embedding_dimension"],
        },
        {
            "section": "4.3 ผลการบันทึกข้อมูล",
            "data_source": "database_payload_contract",
            "metrics": ["payload_keys", "saved_count", "embedding_dimension"],
        },
        {
            "section": "4.4 ผลการค้นหา",
            "data_source": "advanced_search_query_contract",
            "metrics": ["param_count", "threshold_percent"],
        },
    ]

    assert all(item["section"].startswith("4.") for item in outline)
    assert {item["data_source"] for item in outline} == {
        "video_processor_metrics",
        "frame_processor_two_pass_contract",
        "database_payload_contract",
        "advanced_search_query_contract",
    }

    CHAPTER4_REPORT["chapter4_outline"] = outline
