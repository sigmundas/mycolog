# ![MycoLog](docs/images/mycolog-logo.png)

MycoLog is a desktop app for field observations, microscopy calibration, and spore measurements.

## Quick Links

- [Getting started](docs/getting-started.md)
- [Field photography](docs/field-photography.md)
- [Microscopy workflow](docs/microscopy-workflow.md)
- [Spore measurements](docs/spore-measurements.md)
- [Taxonomy integration](docs/taxonomy-integration.md)
- [Database structure](docs/database-structure.md)
- [Changelog](CHANGELOG.md)

## Highlights (recent)

- Objective database uses Magnification + NA, with sampling assessment in calibration and import.
- Calibration history shows camera, megapixels, and exportable overlay images.
- Measurement categories include Spores and Field; a 2-click Line tool supports length-only measurements.
- Analysis supports multiple reference datasets with clearer legend and table labels.
- Gallery tags now show magnification + contrast for microscope images.

## Installation

### Latest release

Download the latest build from:
https://github.com/sigmundas/mycolog/releases/latest

#### Install / run (Windows)
1. Download the `.zip` from the release page.
2. Extract it.
3. Run the `.exe` inside the extracted folder.

### Python installation

```bash
pip install -r requirements.txt
```

```bash
python main.py
```

## Quick Start

1. Create a new observation and import images.
2. Set image type (Field or Micro) and microscope settings where relevant.
3. Calibrate or pick the objective/scale for microscope images.
4. Measure spores (rectangle) or lengths (line) and review in the preview panel.
5. Use Analysis to plot distributions and compare with reference data.

## Screenshots

Automatic calibration of image scales: 
![Calibrate or pick objective](docs/images/calibration.png)

Create a new observation by importing images: 
![Create a new observation](docs/images/1-new-observation.png)

Search-as-you-type species, or use AI lookup to guess the species: 
![Import images](docs/images/2-new-observation.png)

Measure spores or other features: 
![Measure spores or lengths](docs/images/3-measure-spores.png)

Review plots and compare to references: 
![Review analysis and references](docs/images/4-stats-reference.png)

## Data Location

User data is stored in the OS-specific application data folder. See [Database structure](docs/database-structure.md) for details.

- Windows: `%APPDATA%\MycoLog`
- macOS: `~/Library/Application Support/MycoLog`
- Linux: `~/.local/share/MycoLog`

## License

MIT License - feel free to modify and extend.
