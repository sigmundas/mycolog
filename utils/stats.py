"""Statistical calculation utilities."""
import numpy as np
from typing import List, Dict


def calculate_statistics(measurements: List[float]) -> Dict[str, float]:
    """
    Calculate statistical measures for a list of measurements.

    Args:
        measurements: List of measurement values

    Returns:
        Dictionary containing mean, std, min, max, and count
    """
    if not measurements:
        return {
            'mean': 0.0,
            'std': 0.0,
            'min': 0.0,
            'max': 0.0,
            'count': 0
        }

    measurements_array = np.array(measurements)

    return {
        'mean': float(np.mean(measurements_array)),
        'std': float(np.std(measurements_array)),
        'min': float(np.min(measurements_array)),
        'max': float(np.max(measurements_array)),
        'count': len(measurements)
    }


def calculate_confidence_interval(measurements: List[float], confidence: float = 0.95) -> tuple:
    """
    Calculate confidence interval for measurements.

    Args:
        measurements: List of measurement values
        confidence: Confidence level (default 0.95 for 95%)

    Returns:
        Tuple of (lower_bound, upper_bound)
    """
    import scipy.stats as stats

    if len(measurements) < 2:
        return (0.0, 0.0)

    measurements_array = np.array(measurements)
    mean = np.mean(measurements_array)
    std_err = stats.sem(measurements_array)
    interval = std_err * stats.t.ppf((1 + confidence) / 2, len(measurements) - 1)

    return (mean - interval, mean + interval)
