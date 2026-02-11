# Microscopy Workflow

## Objectives

Objectives are defined by:
- Magnification (integer)
- Numerical Aperture (NA)
- Objective name

Display name is built as `<Magnification>X/<NA> <Objective name>` in the UI.

## Calibration

MycoLog supports manual and auto calibration.

- **Manual**: click two points on a known scale.
- **Auto**: detect calibration slide lines, then review the result.

Calibration history stores:
- Camera model
- Megapixels used
- Confidence interval and residuals (when available)

You can export the calibration image with overlays for documentation.

Ideal resolution only appears after the currently loaded calibration image has
an auto result or manual measurements. It is based on the *current image*, not
the previously active calibration.
Calibration images are stored at full resolution; resampling is applied to
imported microscope images and the scale is adjusted by the resample factor.

## Sampling Assessment

Sampling status is shown in the Calibration dialog and Prepare Images panel. This checks if your pixel sampling is undersampled or oversampled based on NA.

### Nyquist Sampling (Basics)

MycoLog uses a Nyquist-based ideal pixel size:

```
ideal_pixel_um = lambda_um / (4 * NA)
```

The default wavelength is violet light at 405 nm (0.405 um). From a calibration scale:

```
pixels_per_micron = 1 / (microns_per_pixel)
ideal_pixels_per_micron = 1 / ideal_pixel_um
sampling_pct = 100 * pixels_per_micron / ideal_pixels_per_micron
```

Rules of thumb:
- <80% is undersampled
- 80-150% is good
- >150% is oversampled

### Downsampling and Scale Propagation

If an image is resampled by a uniform factor `f` (e.g. `f = 0.212`), the scale
and megapixels adjust as:

```
microns_per_pixel_target = microns_per_pixel_full / f
megapixels_target = megapixels_full * f^2
```

MycoLog uses this relationship instead of requiring a second calibration on the
downsampled image.

## Resolution Mismatch Warning

If a microscope image resolution differs significantly from the calibration image, a warning is shown in:
- **Measure** tab (Scale group)
- **Prepare Images** (Scale group)

This is expected for cropped images; the warning includes a tooltip with calibration vs image MP.
The comparison uses the calibration's stored resolution and the image's effective resolution
(taking resampling into account).

## Working with Scale

- Select an objective in the Scale dropdown.
- Use **Set scale...** for custom scale bars.
- For microscope images, ensure the correct objective is applied before measuring.

## Scale Bar Calibration (Manual)

If you need a custom scale (field images or slides without an objective profile):

1. Choose **Scale bar** in the Scale dropdown.
2. Click **Set scale...** and enter the real-world length.
3. Click two points on the scale bar in the image.

You can also trigger this dialog from the **No Scale Set** prompt when you start measuring.

## See also

- [Getting started](getting-started.md)
- [Spore measurements](spore-measurements.md)
- [Database structure](database-structure.md)
