"""Machine Learning Fraud Detection Model for FraudPulse.

Trains, fine-tunes, serializes, and serves an ensemble ML classifier
with feature contribution explainability and calibrated fraud risk scores.
"""

import os
import joblib
import numpy as np
import pandas as pd
from typing import Any, Dict, List, Optional, Tuple
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier, VotingClassifier
from sklearn.calibration import CalibratedClassifierCV

from src.ml.features import FEATURE_COLUMNS, extract_features, extract_features_df
from src.generator import generate_synthetic_transactions

MODEL_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "models")
MODEL_PATH = os.path.join(MODEL_DIR, "fraud_detector.joblib")


class FraudMLModel:
    """Production-grade ML model for transaction risk scoring and feature explainability."""

    def __init__(self, model: Optional[Any] = None):
        self.model = model
        self.feature_columns = FEATURE_COLUMNS
        self.feature_importances: Dict[str, float] = {}

    def train(self, df: Optional[pd.DataFrame] = None) -> Dict[str, Any]:
        """Trains and fine-tunes the ML model on multi-seed synthetic transaction datasets with labeled fraud patterns.

        Args:
            df: Optional training DataFrame. If None, generates a large 600+ multi-pattern corpus.

        Returns:
            Dict containing training metrics and top feature importances.
        """
        if df is None or len(df) == 0:
            # Generate a rich multi-seed dataset with diverse legitimate & fraud patterns
            dfs = []
            for s in [42, 101, 2024, 777]:
                dfs.append(generate_synthetic_transactions(seed=s, num_users=25, num_tx=160))
            df = pd.concat(dfs, ignore_index=True)

        # Extract features for full chronological dataset
        X_df = extract_features_df(df)
        y = df["is_fraud"].astype(int).values

        # Base Ensemble: Tuned Random Forest + Gradient Boosting
        rf = RandomForestClassifier(
            n_estimators=150,
            max_depth=7,
            min_samples_split=3,
            min_samples_leaf=2,
            random_state=42,
            class_weight="balanced",
        )
        gb = GradientBoostingClassifier(
            n_estimators=120,
            learning_rate=0.08,
            max_depth=5,
            random_state=42,
        )

        ensemble = VotingClassifier(
            estimators=[("rf", rf), ("gb", gb)],
            voting="soft",
        )
        ensemble.fit(X_df[self.feature_columns], y)

        # Calibrated Classifier for smooth, well-calibrated probabilities
        self.model = CalibratedClassifierCV(estimator=ensemble, cv=3)
        self.model.fit(X_df[self.feature_columns], y)

        # Fit RF separately to extract feature importances
        rf.fit(X_df[self.feature_columns], y)
        importances = rf.feature_importances_
        self.feature_importances = {
            col: round(float(imp), 4) for col, imp in zip(self.feature_columns, importances)
        }

        # Ensure model directory exists and save
        os.makedirs(MODEL_DIR, exist_ok=True)
        joblib.dump({"model": self.model, "importances": self.feature_importances}, MODEL_PATH)

        train_acc = float(np.mean(self.model.predict(X_df[self.feature_columns]) == y))

        return {
            "samples_trained": len(df),
            "fraud_samples": int(np.sum(y)),
            "train_accuracy": round(train_acc, 4),
            "feature_importances": self.feature_importances,
        }

    def load(self, path: str = MODEL_PATH) -> bool:
        """Loads a pre-trained model artifact from disk."""
        if os.path.exists(path):
            try:
                data = joblib.load(path)
                self.model = data["model"]
                self.feature_importances = data.get("importances", {})
                return True
            except Exception as e:
                print(f"Warning: Failed to load model from {path}: {e}")
                return False
        return False

    def predict(
        self,
        tx: Dict[str, Any],
        history_df: pd.DataFrame,
    ) -> Dict[str, Any]:
        """Predicts ML fraud risk score and explainable feature contributions for a transaction.

        Args:
            tx: Target transaction dict.
            history_df: Historical transactions DataFrame prior to this transaction.

        Returns:
            Dict containing:
            - ml_risk_score: float [0.0, 1.0]
            - is_flagged: bool
            - ml_signals: List[str]
            - feature_contributions: Dict[str, Any]
            - feature_vector: Dict[str, float]
        """
        if self.model is None:
            if not self.load():
                self.train()

        feat_dict = extract_features(tx, history_df)
        feat_df = pd.DataFrame([feat_dict])[self.feature_columns]

        # Predict probability of fraud (class 1)
        proba = float(self.model.predict_proba(feat_df)[0, 1])
        ml_risk_score = round(proba, 2)
        is_flagged = ml_risk_score >= 0.35

        # Determine active ML signals based on feature deviations
        ml_signals: List[str] = []
        feature_contributions: Dict[str, Any] = {}

        if feat_dict["amount_to_mean_ratio"] > 2.5:
            ml_signals.append("ML_AMOUNT_ANOMALY")
            feature_contributions["Amount Spike"] = f"{feat_dict['amount_to_mean_ratio']:.1f}x Historical Mean"

        if feat_dict["velocity_10m"] >= 2:
            ml_signals.append("ML_VELOCITY_BURST")
            feature_contributions["Velocity Burst"] = f"{int(feat_dict['velocity_10m'])} txs in 10m"

        if feat_dict["is_new_device"] == 1.0:
            ml_signals.append("ML_UNFAMILIAR_DEVICE")
            feature_contributions["Unfamiliar Device"] = tx.get("device_id", "Unknown")

        if feat_dict["is_new_city"] == 1.0:
            ml_signals.append("ML_UNFAMILIAR_LOCATION")
            feature_contributions["Location Jump"] = tx.get("city", "Unknown")

        if feat_dict["user_prior_disputes"] > 0:
            ml_signals.append("ML_HISTORICAL_DISPUTES")
            feature_contributions["Prior Disputes"] = f"{int(feat_dict['user_prior_disputes'])} record(s)"

        if is_flagged and not ml_signals:
            ml_signals.append("ML_FRAUD_PREDICTION")
            feature_contributions["Model Confidence"] = f"Statistical Risk Score {ml_risk_score:.2f}"

        return {
            "ml_risk_score": ml_risk_score,
            "is_flagged": is_flagged,
            "ml_signals": ml_signals,
            "feature_contributions": feature_contributions,
            "feature_vector": feat_dict,
        }


# Singleton Model Instance
_global_model: Optional[FraudMLModel] = None


def get_fraud_model() -> FraudMLModel:
    """Returns the singleton initialized FraudMLModel instance."""
    global _global_model
    if _global_model is None:
        _global_model = FraudMLModel()
        if not _global_model.load():
            _global_model.train()
    return _global_model


if __name__ == "__main__":
    print("Fine-tuning FraudPulse ML Model on multi-pattern dataset...")
    model = FraudMLModel()
    metrics = model.train()
    print("Fine-tuning complete! Metrics:", metrics)
