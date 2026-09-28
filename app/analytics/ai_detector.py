import logging
import numpy as np

try:
    from sklearn.ensemble import IsolationForest
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False

logger = logging.getLogger(__name__)

class PressureAnomalyDetector:
    def __init__(self):
        self.model = None
        self.is_trained = False
        if SKLEARN_AVAILABLE:
            self.model = IsolationForest(
                n_estimators=50,
                contamination=0.05,
                random_state=42
            )

    def train(self, history_data):
        """
        Train the Isolation Forest model on historical normal data.
        """
        if not SKLEARN_AVAILABLE or not history_data:
            return

        features = []
        for record in history_data:
            if record.get('status') == 'normal':
                features.append([record.get('deviation_percent', 0.0)])

        if len(features) < 10:
            return

        try:
            X = np.array(features)
            self.model.fit(X)
            self.is_trained = True
            logger.info("IsolationForest model successfully trained.")
        except Exception as e:
            logger.error(f"Error training AI model: {e}")
            self.is_trained = False

    def predict(self, current_pressure, baseline_pressure):
        """
        Predict if the current pressure is an anomaly.
        """
        deviation_percent = 0.0
        if baseline_pressure > 0:
            deviation_percent = ((current_pressure - baseline_pressure) / baseline_pressure) * 100

        # Constants for rule-based (fallback) logic
        threshold = 15.0
        rule_based_anomaly = abs(deviation_percent) > threshold

        if not self.is_trained or not SKLEARN_AVAILABLE:
            return {
                "is_anomaly": rule_based_anomaly,
                "score": -1.0 if rule_based_anomaly else 1.0,
                "confidence": 50.0,
                "explanation": (
                    f"Pressure deviates by {abs(deviation_percent):.1f}% from baseline and is classified as anomalous by rule-based fallback."
                    if rule_based_anomaly else
                    "Pressure is within expected operating range based on historical patterns."
                )
            }

        try:
            X = np.array([[current_pressure, baseline_pressure, deviation_percent]])
            pred = self.model.predict(X)[0] # -1 for anomaly, 1 for normal
            score = self.model.decision_function(X)[0]
            
            is_anomaly = bool(pred == -1)
            
            # HYBRID LOGIC: final anomaly if AI says so OR deviation is huge
            final_anomaly = is_anomaly or rule_based_anomaly
            
            # Normalize confidence slightly based on score
            confidence = min(99.0, max(50.0, float(abs(score)) * 100 + 50))
            
            if final_anomaly:
                explanation = f"Pressure deviates by {abs(deviation_percent):.1f}% from baseline and is classified as anomalous by Isolation Forest model."
            else:
                explanation = "Pressure is within expected operating range based on historical patterns."
                
            return {
                "is_anomaly": final_anomaly,
                "score": float(score),
                "confidence": round(confidence, 1),
                "explanation": explanation
            }
        except Exception as e:
            logger.error(f"Error predicting with AI model: {e}")
            return {
                "is_anomaly": rule_based_anomaly,
                "score": -1.0 if rule_based_anomaly else 1.0,
                "confidence": 50.0,
                "explanation": (
                    f"Pressure deviates by {abs(deviation_percent):.1f}% from baseline and is classified as anomalous by fallback logic due to error."
                    if rule_based_anomaly else
                    "Pressure is within expected operating range based on historical patterns (fallback logic)."
                )
            }

    def predict_batch(self, payload_list):
        """
        Predict if the current pressure is an anomaly for a batch of sensors.
        Optimized to use a single call to model.predict.
        """
        if not payload_list:
            return []

        results = []
        X_features = []
        rule_based_flags = []
        deviation_percents = []

        for item in payload_list:
            c = item["current_pressure"]
            b = item["baseline_pressure"]
            dev = 0.0
            if b > 0:
                dev = ((c - b) / b) * 100
            
            deviation_percents.append(dev)
            rule_based_flags.append(abs(dev) > 15.0)
            X_features.append([dev])
            
        if not self.is_trained or not SKLEARN_AVAILABLE:
            for i, rule_anomaly in enumerate(rule_based_flags):
                dev = deviation_percents[i]
                results.append({
                    "is_anomaly": rule_anomaly,
                    "score": -1.0 if rule_anomaly else 1.0,
                    "confidence": 50.0,
                    "explanation": (
                        f"Pressure deviates by {abs(dev):.1f}% from baseline and is classified as anomalous by rule-based fallback."
                        if rule_anomaly else
                        "Pressure is within expected operating range based on historical patterns."
                    )
                })
            return results
            
        try:
            X = np.array(X_features)
            preds = self.model.predict(X)
            scores = self.model.decision_function(X)
            
            for i in range(len(payload_list)):
                is_anomaly = bool(preds[i] == -1)
                rule_anomaly = rule_based_flags[i]
                final_anomaly = is_anomaly or rule_anomaly
                dev = deviation_percents[i]
                score = float(scores[i])
                confidence = min(99.0, max(50.0, float(abs(score)) * 100 + 50))
                
                if final_anomaly:
                    explanation = f"Pressure deviates by {abs(dev):.1f}% from baseline and is classified as anomalous by Isolation Forest model."
                else:
                    explanation = "Pressure is within expected operating range based on historical patterns."
                    
                results.append({
                    "is_anomaly": final_anomaly,
                    "score": score,
                    "confidence": round(confidence, 1),
                    "explanation": explanation
                })
            return results
        except Exception as e:
            logger.error(f"Error predicting batch with AI model: {e}")
            for i, rule_anomaly in enumerate(rule_based_flags):
                dev = deviation_percents[i]
                results.append({
                    "is_anomaly": rule_anomaly,
                    "score": -1.0 if rule_anomaly else 1.0,
                    "confidence": 50.0,
                    "explanation": (
                        f"Pressure deviates by {abs(dev):.1f}% from baseline and is classified as anomalous by fallback logic due to error."
                        if rule_anomaly else
                        "Pressure is within expected operating range based on historical patterns (fallback logic)."
                    )
                })
            return results

# Singleton instance
ai_detector = PressureAnomalyDetector()
