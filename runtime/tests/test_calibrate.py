import json
from pathlib import Path

from conftest import make_detection, make_frame

from video_runtime.config import BindingConfig, RuntimeConfig
from video_runtime.event_builder import EventBinding, binding_from_config
from video_runtime.frame import Frame
from video_runtime.inference.base import Detection
from video_runtime.tools.calibrate import (
    Analysis,
    SopCondition,
    _matching_confidences,
    analyze,
    apply_binding_thresholds,
    apply_sop_thresholds,
    replace_min_conf,
    sop_conditions,
    suggest_completion,
)

YAML = """bindings:
  # keep this comment
  - event_type: batteries_installed
    primitive: count_threshold
    params:
      object_class: battery
      min_conf: 0.5
  - event_type: remote_present
    primitive: object_present
    params:
      object_class: remote
      min_conf: 0.25
"""


class FakeDetector:
    def __init__(self, detections: list[Detection]) -> None:
        self._detections = detections

    def infer(self, frame: Frame) -> list[Detection]:
        return self._detections


def count_binding() -> EventBinding:
    return binding_from_config(
        BindingConfig(
            event_type="batteries_installed",
            primitive="count_threshold",
            params={
                "object_class": "battery",
                "count_classes": ["CORRECT", "REVERSED"],
                "compartment": "remote",
                "roi": [0.0, 0.0, 1.0, 1.0],
                "slots": 2,
                "min_conf": 0.25,
            },
        )
    )


def test_analyze_collects_class_and_event_stats() -> None:
    detections = [
        make_detection("battery", 0.8, (0.1, 0.1, 0.2, 0.2)),
        make_detection("CORRECT", 0.6, (0.5, 0.5, 0.6, 0.6)),
    ]

    analysis = analyze(
        (make_frame(seq=index) for index in range(3)),
        FakeDetector(detections),
        [count_binding()],
    )

    assert analysis.frames == 3
    assert analysis.class_confidences["battery"] == [0.8, 0.8, 0.8]
    assert analysis.event_frames["batteries_installed"] == 3
    assert analysis.event_confidences["batteries_installed"] == [0.7, 0.7, 0.7]
    assert analysis.counts["batteries_installed"][2] == 3
    assert (
        analysis.roi_hits["batteries_installed"]
        == [
            ("battery", True),
            ("CORRECT", True),
        ]
        * 3
    )


def test_suggest_completion_uses_the_tenth_percentile_with_a_floor() -> None:
    assert suggest_completion([]) is None
    assert suggest_completion([0.72] * 10) == 0.72
    assert suggest_completion([0.1] * 5 + [0.9] * 5) == 0.3
    assert suggest_completion([1.0] * 10) == 0.95


def test_sop_conditions_reads_all_and_any(tmp_path: Path) -> None:
    path = tmp_path / "sop.json"
    path.write_text(
        json.dumps(
            {
                "steps": [
                    {
                        "key": "step",
                        "completion": {
                            "all": [
                                {
                                    "event_type": "a",
                                    "min_confidence": 0.9,
                                    "attributes": {"count": {"gte": 2}},
                                }
                            ],
                            "any": [{"event_type": "b"}],
                        },
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    conditions = sop_conditions(path)

    assert [
        (condition.step_key, condition.event_type, condition.min_confidence)
        for condition in conditions
    ] == [("step", "a", 0.9), ("step", "b", 0.0)]
    assert conditions[0].attributes == {"count": {"gte": 2}}
    assert conditions[1].attributes == {}


def test_condition_filtering_applies_attribute_predicates() -> None:
    analysis = Analysis()
    analysis.event_samples["batteries_installed"] = [
        ({"count": 1, "slots": 2}, 0.9),
        ({"count": 2, "slots": 2}, 0.6),
    ]
    condition = SopCondition(
        step_key="insert",
        event_type="batteries_installed",
        min_confidence=0.9,
        attributes={"count": {"gte": 2}, "slots": {"eq": 2}},
    )

    assert _matching_confidences(analysis, condition) == [0.6]


def test_apply_sop_thresholds_writes_and_backs_up(tmp_path: Path) -> None:
    path = tmp_path / "sop.json"
    path.write_text(
        json.dumps(
            {
                "steps": [
                    {
                        "key": "insert",
                        "completion": {
                            "all": [
                                {
                                    "event_type": "batteries_installed",
                                    "min_confidence": 0.9,
                                }
                            ]
                        },
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    backup, changes = apply_sop_thresholds(path, {"batteries_installed": 0.55})

    assert changes == ["insert:batteries_installed 0.9 -> 0.55"]
    assert backup is not None and backup.is_file()
    data = json.loads(path.read_text(encoding="utf-8"))
    condition = data["steps"][0]["completion"]["all"][0]
    assert condition["min_confidence"] == 0.55
    assert apply_sop_thresholds(path, {"batteries_installed": 0.55}) == (None, [])


def test_apply_sop_thresholds_preserves_formatting(tmp_path: Path) -> None:
    path = tmp_path / "sop.json"
    path.write_text(
        '{\n  "steps": [\n    {\n      "key": "insert",\n'
        '      "completion": {\n        "all": [\n          {\n'
        '            "event_type": "batteries_installed",\n'
        '            "min_confidence": 0.9,\n'
        '            "attributes": {"count": {"gte": 2}}\n'
        "          }\n        ]\n      }\n    }\n  ]\n}\n",
        encoding="utf-8",
    )

    apply_sop_thresholds(path, {"batteries_installed": 0.55})

    updated = path.read_text(encoding="utf-8")
    assert '"attributes": {"count": {"gte": 2}}' in updated
    assert '"min_confidence": 0.55' in updated


def test_replace_min_conf_preserves_comments_and_other_bindings() -> None:
    updated = replace_min_conf(YAML, "batteries_installed", 0.3)

    assert "# keep this comment" in updated
    assert "min_conf: 0.30" in updated
    assert "min_conf: 0.25" in updated


def test_apply_binding_thresholds_lowers_only_high_values(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text(YAML, encoding="utf-8")
    config = RuntimeConfig(
        runtime_id="runtime-01",
        station_id="st-01",
        camera={
            "camera_id": "cam-01",
            "role": "overview",
            "source": {"kind": "file", "path": "clip.avi"},
        },
        backend={"base_url": "http://127.0.0.1:8000/api"},
        model={"onnx_path": "model.onnx", "class_names_path": "names.txt"},
        evidence_dir=tmp_path,
        bindings=[
            {
                "event_type": "batteries_installed",
                "primitive": "count_threshold",
                "params": {
                    "object_class": "battery",
                    "compartment": "remote",
                    "roi": [0.0, 0.0, 1.0, 1.0],
                    "min_conf": 0.5,
                },
            }
        ],
    )

    changes = apply_binding_thresholds(
        path,
        config,
        {"batteries_installed": 0.3, "remote_present": 0.3},
    )

    assert changes == ["batteries_installed: min_conf 0.5 -> 0.30"]
    text = path.read_text(encoding="utf-8")
    assert "min_conf: 0.30" in text
    assert "min_conf: 0.25" in text
