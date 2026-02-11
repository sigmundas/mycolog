# Getting Started

## Overview

MycoLog helps you organize field observations, calibrate microscopy images, and measure spores or other structures. This guide covers installation and a minimal first workflow.

## Installation

### Latest release

Download the latest build:
https://github.com/sigmundas/mycolog/releases/latest

### Python

```bash
pip install -r requirements.txt
python main.py
```

## First Run Checklist

1. Open `Calibration > Microscope Objectives`.
2. Add or edit objectives (Magnification, NA, Objective name).
3. Calibrate an objective (auto or manual) and set it active.
4. Confirm your database folder in `Settings > Database`.

## Create Your First Observation

1. Click **New Observation**.
2. Add images (field or microscope). Multi-select is supported.
3. For microscope images, choose Objective/Scale, Contrast, Mount, and Sample type.
4. Use **Apply to all** to copy settings to selected images.
5. Save the observation.

## Measure and Analyze

- Use the **Measure** tab to draw rectangles for spores or line measurements for length-only.
- Use **Analysis** to plot distributions and compare with reference datasets.

## See also

- [Field photography](field-photography.md)
- [Microscopy workflow](microscopy-workflow.md)
- [Spore measurements](spore-measurements.md)
- [Taxonomy integration](taxonomy-integration.md)
- [Database structure](database-structure.md)
