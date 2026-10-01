"""Tests for data contracts."""

from pathlib import Path

import pytest

from canvastekk_workflow_sdk.contracts import (
    STANDARD_CLASS_NAMES,
    STANDARD_CLASSES,
    BoundingBox3D,
    Instance,
    InstanceSet,
    Measurement,
    MeasurementSet,
    Plane,
    PlaneSet,
    build_check_output_schema,
    validate_verdict_fields,
    Point3D,
)


class TestPoint3D:
    def test_create(self) -> None:
        p = Point3D(x=1.0, y=2.0, z=3.0)
        assert p.x == 1.0
        assert p.y == 2.0
        assert p.z == 3.0

    def test_to_list(self) -> None:
        p = Point3D(x=1.0, y=2.0, z=3.0)
        assert p.to_list() == [1.0, 2.0, 3.0]

    def test_from_list(self) -> None:
        p = Point3D.from_list([4.0, 5.0, 6.0])
        assert p.x == 4.0
        assert p.y == 5.0
        assert p.z == 6.0

    def test_roundtrip(self) -> None:
        original = Point3D(x=1.5, y=2.5, z=3.5)
        restored = Point3D.from_list(original.to_list())
        assert restored == original


class TestBoundingBox3D:
    @pytest.fixture
    def bbox(self) -> BoundingBox3D:
        return BoundingBox3D(
            min_point=Point3D(x=0.0, y=0.0, z=0.0),
            max_point=Point3D(x=10.0, y=20.0, z=30.0),
        )

    def test_center(self, bbox: BoundingBox3D) -> None:
        center = bbox.center
        assert center.x == 5.0
        assert center.y == 10.0
        assert center.z == 15.0

    def test_size(self, bbox: BoundingBox3D) -> None:
        size = bbox.size
        assert size.x == 10.0
        assert size.y == 20.0
        assert size.z == 30.0

    def test_zero_size(self) -> None:
        p = Point3D(x=5.0, y=5.0, z=5.0)
        bbox = BoundingBox3D(min_point=p, max_point=p)
        assert bbox.size.x == 0.0
        assert bbox.center.x == 5.0


class TestPlane:
    def test_create_with_label(self) -> None:
        plane = Plane(
            point=Point3D(x=0, y=0, z=0),
            normal=Point3D(x=0, y=0, z=1),
            label="floor",
        )
        assert plane.label == "floor"

    def test_create_without_label(self) -> None:
        plane = Plane(
            point=Point3D(x=1, y=2, z=3),
            normal=Point3D(x=0, y=1, z=0),
        )
        assert plane.label is None


class TestInstance:
    @pytest.fixture
    def instance(self) -> Instance:
        return Instance(
            instance_id=0,
            class_id=4,
            class_name="vent",
            confidence=0.95,
            point_indices=[0, 1, 2, 3, 4],
            centroid=Point3D(x=1.0, y=2.0, z=3.0),
        )

    def test_num_points(self, instance: Instance) -> None:
        assert instance.num_points == 5

    def test_default_confidence(self) -> None:
        inst = Instance(
            instance_id=0,
            class_id=0,
            class_name="floor",
            point_indices=[0],
        )
        assert inst.confidence == 1.0

    def test_default_metadata(self, instance: Instance) -> None:
        assert instance.metadata == {}

    def test_confidence_bounds(self) -> None:
        with pytest.raises(Exception):
            Instance(
                instance_id=0,
                class_id=0,
                class_name="x",
                point_indices=[],
                confidence=1.5,
            )


class TestInstanceSet:
    @pytest.fixture
    def instance_set(self) -> InstanceSet:
        return InstanceSet(
            instances=[
                Instance(instance_id=0, class_id=0, class_name="floor", point_indices=[0, 1]),
                Instance(instance_id=1, class_id=4, class_name="vent", point_indices=[2, 3]),
                Instance(instance_id=2, class_id=4, class_name="vent", point_indices=[4, 5]),
            ],
            class_names=["floor", "ceiling", "wall", "door", "vent"],
            point_count=6,
            source_node="segmentation",
        )

    def test_get_instances_by_class(self, instance_set: InstanceSet) -> None:
        vents = instance_set.get_instances_by_class("vent")
        assert len(vents) == 2
        assert all(i.class_name == "vent" for i in vents)

    def test_get_instances_by_class_id(self, instance_set: InstanceSet) -> None:
        floors = instance_set.get_instances_by_class_id(0)
        assert len(floors) == 1
        assert floors[0].class_name == "floor"

    def test_get_instances_by_class_empty(self, instance_set: InstanceSet) -> None:
        result = instance_set.get_instances_by_class("nonexistent")
        assert result == []

    def test_save_and_load_json(self, instance_set: InstanceSet, tmp_path: Path) -> None:
        path = tmp_path / "instances.json"
        instance_set.save_json(path)

        assert path.exists()
        loaded = InstanceSet.load_json(path)
        assert len(loaded.instances) == 3
        assert loaded.source_node == "segmentation"
        assert loaded.point_count == 6

    def test_json_roundtrip_preserves_data(self, instance_set: InstanceSet, tmp_path: Path) -> None:
        path = tmp_path / "roundtrip.json"
        instance_set.save_json(path)
        loaded = InstanceSet.load_json(path)

        assert loaded.instances[0].class_name == "floor"
        assert loaded.instances[1].point_indices == [2, 3]
        assert loaded.class_names == ["floor", "ceiling", "wall", "door", "vent"]

    def test_default_contract_version(self, instance_set: InstanceSet) -> None:
        assert instance_set.contract_version == "1.0.0"

    def test_empty_instance_set(self) -> None:
        empty = InstanceSet()
        assert empty.instances == []
        assert empty.point_count == 0
        assert empty.get_instances_by_class("floor") == []


class TestMeasurement:
    def test_create(self) -> None:
        m = Measurement(name="height", value=2500.0, unit="mm")
        assert m.name == "height"
        assert m.value == 2500.0
        assert m.unit == "mm"
        assert m.method == "unknown"
        assert m.confidence == 1.0

    def test_with_points(self) -> None:
        m = Measurement(
            name="distance",
            value=100.0,
            points=[Point3D(x=0, y=0, z=0), Point3D(x=100, y=0, z=0)],
        )
        assert len(m.points) == 2


class TestMeasurementSet:
    @pytest.fixture
    def measurement_set(self) -> MeasurementSet:
        return MeasurementSet(
            measurements=[
                Measurement(name="height", value=2500.0, unit="mm"),
                Measurement(name="width", value=3000.0, unit="mm"),
            ],
            source_node="dimension-check",
        )

    def test_get_measurement(self, measurement_set: MeasurementSet) -> None:
        m = measurement_set.get_measurement("height")
        assert m is not None
        assert m.value == 2500.0

    def test_get_measurement_not_found(self, measurement_set: MeasurementSet) -> None:
        assert measurement_set.get_measurement("depth") is None

    def test_get_value(self, measurement_set: MeasurementSet) -> None:
        assert measurement_set.get_value("width") == 3000.0

    def test_get_value_default(self, measurement_set: MeasurementSet) -> None:
        assert measurement_set.get_value("depth", default=0.0) == 0.0

    def test_get_value_not_found_no_default(self, measurement_set: MeasurementSet) -> None:
        assert measurement_set.get_value("depth") is None

    def test_save_and_load_json(self, measurement_set: MeasurementSet, tmp_path: Path) -> None:
        path = tmp_path / "measurements.json"
        measurement_set.save_json(path)

        loaded = MeasurementSet.load_json(path)
        assert len(loaded.measurements) == 2
        assert loaded.source_node == "dimension-check"
        assert loaded.get_value("height") == 2500.0


class TestPlaneSet:
    @pytest.fixture
    def plane_set(self) -> PlaneSet:
        return PlaneSet(
            planes=[
                Plane(
                    point=Point3D(x=0, y=0, z=0),
                    normal=Point3D(x=0, y=0, z=1),
                    label="floor",
                ),
                Plane(
                    point=Point3D(x=0, y=0, z=3),
                    normal=Point3D(x=0, y=0, z=-1),
                    label="ceiling",
                ),
            ],
            source_node="detect-planes",
        )

    def test_get_plane_by_label(self, plane_set: PlaneSet) -> None:
        floor = plane_set.get_plane_by_label("floor")
        assert floor is not None
        assert floor.normal.z == 1.0

    def test_get_plane_by_label_not_found(self, plane_set: PlaneSet) -> None:
        assert plane_set.get_plane_by_label("wall") is None

    def test_save_and_load_json(self, plane_set: PlaneSet, tmp_path: Path) -> None:
        path = tmp_path / "planes.json"
        plane_set.save_json(path)

        loaded = PlaneSet.load_json(path)
        assert len(loaded.planes) == 2
        assert loaded.source_node == "detect-planes"

    def test_empty_plane_set(self) -> None:
        ps = PlaneSet()
        assert ps.planes == []
        assert ps.get_plane_by_label("floor") is None


class TestStandardClasses:
    def test_standard_classes(self) -> None:
        assert STANDARD_CLASSES[0] == "floor"
        assert STANDARD_CLASSES[4] == "vent"
        assert len(STANDARD_CLASSES) == 5

    def test_standard_class_names(self) -> None:
        assert STANDARD_CLASS_NAMES == ["floor", "ceiling", "wall", "door", "vent"]


class TestBuildCheckOutputSchema:
    """DA-3359: the shared check-node output-contract builder."""

    def test_default_vocab_and_shape(self) -> None:
        schema = build_check_output_schema()
        assert schema["properties"]["verdict"]["enum"] == ["PASS", "FAIL", "NOT_EVALUABLE"]
        assert schema["properties"]["result"]["required"] == ["verdict"]
        assert "additionalProperties" not in schema

    def test_custom_vocab(self) -> None:
        schema = build_check_output_schema(("CLEAR", "VIOLATION"), "Seam check.")
        assert schema["properties"]["verdict"]["enum"] == ["CLEAR", "VIOLATION"]
        assert schema["properties"]["result"]["description"] == "Seam check."

    def test_closed_flag_both_levels(self) -> None:
        schema = build_check_output_schema(closed=True)
        assert schema["additionalProperties"] is False
        assert schema["properties"]["result"]["additionalProperties"] is False
        # the error property survives the closure so ErrorOutputNode appends validate
        assert "error" in schema["properties"]

    def test_closed_schema_accepts_error_append(self) -> None:
        import jsonschema

        schema = build_check_output_schema(closed=True)
        payload = {
            "verdict": "FAIL",
            "result": {"verdict": "FAIL"},
            "error": {"message": "boom"},
        }
        jsonschema.validate(payload, schema)

    def test_open_schema_rejects_unknown_when_validated(self) -> None:
        import jsonschema

        schema = build_check_output_schema()
        jsonschema.validate({"verdict": "PASS", "result": {"verdict": "PASS"}}, schema)


class TestValidateVerdictFields:
    def test_accepts_valid_payload(self) -> None:
        validate_verdict_fields({"verdict": "PASS", "result": {"verdict": "PASS"}})

    def test_rejects_off_vocab_headline(self) -> None:
        with pytest.raises(ValueError, match="verdict"):
            validate_verdict_fields({"verdict": "SKIP", "result": {"verdict": "PASS"}})

    def test_rejects_missing_result(self) -> None:
        with pytest.raises(ValueError, match="result"):
            validate_verdict_fields({"verdict": "PASS"})

    def test_rejects_off_vocab_result_verdict(self) -> None:
        with pytest.raises(ValueError, match="result.verdict"):
            validate_verdict_fields({"verdict": "PASS", "result": {"verdict": "MAYBE"}})


class TestImportGraph:
    """DA-3359: contracts is opt-in — core modules never import it."""

    @pytest.mark.parametrize("module_name", ["app", "base"])
    def test_core_modules_do_not_import_contracts(self, module_name: str) -> None:
        import ast
        import importlib.util

        spec = importlib.util.find_spec(f"canvastekk_workflow_sdk.{module_name}")
        assert spec is not None and spec.origin
        tree = ast.parse(open(spec.origin).read())
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                assert all("contracts" not in a.name for a in node.names), node.names
            elif isinstance(node, ast.ImportFrom):
                assert "contracts" not in (node.module or ""), node.module
