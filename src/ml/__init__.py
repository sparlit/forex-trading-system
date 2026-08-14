"""ML utilities – feature store & online learning."""
from src.ml.feature_store import (
    FeatureStore,
    FeatureVector,
    OnlineLinearModel,
    get_feature_store,
)

__all__ = [
    "FeatureStore",
    "FeatureVector",
    "OnlineLinearModel",
    "get_feature_store",
]
