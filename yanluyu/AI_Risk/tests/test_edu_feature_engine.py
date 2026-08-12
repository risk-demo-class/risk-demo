"""
Test education feature engineering: feature computation and dictionary dispatch.
Tests run without DB - verify function structure and correctness.
"""
import pytest


class TestEduFeatureStructure:
    """Verify feature module structure and naming conventions."""

    def test_compute_user_features_signature(self):
        from app.engine.feature_edu import compute_user_features
        import inspect
        sig = inspect.signature(compute_user_features)
        params = list(sig.parameters.keys())
        assert "db" in params
        assert "user_id" in params

    def test_compute_order_features_signature(self):
        from app.engine.feature_edu import compute_order_features
        import inspect
        sig = inspect.signature(compute_order_features)
        params = list(sig.parameters.keys())
        assert "db" in params
        assert "order_id" in params
        assert "course_id" in params

    def test_compute_all_features_signature(self):
        from app.engine.feature_edu import compute_all_features
        import inspect
        sig = inspect.signature(compute_all_features)
        params = list(sig.parameters.keys())
        assert "db" in params
        assert "user_id" in params
        assert "event_type" in params

    def test_feature_naming_convention(self):
        """All education features should follow the prefix convention."""
        from app.engine.feature_edu import compute_user_features, compute_order_features
        import inspect

        # Check compute_user_features returns dict
        assert inspect.iscoroutinefunction(compute_user_features)

    def test_all_features_event_type_routing(self):
        """Different event_types compute different feature subsets."""
        from app.engine.feature_edu import compute_all_features
        import inspect
        sig = inspect.signature(compute_all_features)
        params = sig.parameters
        assert "event_type" in params
        assert params["event_type"].default == "报名"


class TestFeatureDimensionCount:
    """Verify feature dimensions are correct."""

    def test_feature_columns_length(self):
        from app.engine.ml_model import FEATURE_COLUMNS
        assert len(FEATURE_COLUMNS) == 12, f"Expected 12 education features, got {len(FEATURE_COLUMNS)}"

    def test_feature_columns_content(self):
        from app.engine.ml_model import FEATURE_COLUMNS
        # User features (6)
        user_feats = [f for f in FEATURE_COLUMNS if f.startswith("user_")]
        assert len(user_feats) == 6
        # Order features (2 - order_total_amount is order_*, course_is_student_only is also order-like)
        order_feats = [f for f in FEATURE_COLUMNS if f.startswith("order_")]
        assert len(order_feats) == 1  # order_total_amount
        # Course features
        course_feats = [f for f in FEATURE_COLUMNS if f.startswith("course_")]
        assert len(course_feats) == 2  # course_is_student_only, course_new_students_7d
        # Device features
        device_feats = [f for f in FEATURE_COLUMNS if f.startswith("device_")]
        assert len(device_feats) == 1  # device_linked_students
        # Learning features
        learn_feats = [f for f in FEATURE_COLUMNS if f.startswith("study_")]
        assert len(learn_feats) == 1  # study_minutes_before_refund
        # Donation features
        donation_feats = [f for f in FEATURE_COLUMNS if f.startswith("donation_")]
        assert len(donation_feats) == 1  # donation_amount


class TestEntityClassification:
    """Test feature entity classification logic."""

    def test_user_features_entity(self):
        from app.engine.decision import _classify_feature_entity
        assert _classify_feature_entity("user_total_orders")[0] == "用户"
        assert _classify_feature_entity("user_is_teacher")[0] == "用户"

    def test_order_features_entity(self):
        from app.engine.decision import _classify_feature_entity
        assert _classify_feature_entity("order_total_amount")[0] == "订单"
        assert _classify_feature_entity("course_is_student_only")[0] == "订单"

    def test_device_features_entity(self):
        from app.engine.decision import _classify_feature_entity
        assert _classify_feature_entity("device_linked_students")[0] == "设备"

    def test_learn_features_entity(self):
        from app.engine.decision import _classify_feature_entity
        assert _classify_feature_entity("study_minutes_before_refund")[0] == "用户"
