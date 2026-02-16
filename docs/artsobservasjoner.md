# Artsobservasjoner Login and Upload

This guide explains how to log in to Artsobservasjoner and upload observations from MycoLog.

## Login

1. Open **Settings -> Artsobservasjoner**.
2. Click **Log in to Artsobservasjoner** and complete the login in the embedded browser window.
3. After a successful login, MycoLog stores cookies so you stay logged in between restarts.

Cookies are cached in the MycoLog app data folder as `artsobservasjoner_cookies.json`:

- Windows: `%APPDATA%\\MycoLog\\artsobservasjoner_cookies.json`
- macOS: `~/Library/Application Support/MycoLog/artsobservasjoner_cookies.json`
- Linux: `~/.local/share/MycoLog/artsobservasjoner_cookies.json`

If cookies expire, return to **Settings -> Artsobservasjoner** and re-authenticate.

## Upload an observation

1. Go to the **Observations** tab.
2. Select the observation you want to upload.
3. Click **Upload to Artsobs**.

The progress dialog will show which step is running and the image count (for example, "Uploading image 2/3").

## Requirements

Uploads require:

- Genus and species set (so an Artsdatabanken taxon id is available).
- Observation date.
- GPS coordinates (lat/lon).
- At least one image of type **Field** or **Microscope**.

## Upload target

In **Settings -> Artsobservasjoner**, you can choose the upload target:

- **Artsobservasjoner (mobile)**: Uses the mobile API and supports image uploads.
- **Artsobservasjoner (web)**: Uses the web form endpoints and submits habitat + notes (images are not uploaded yet).

The web uploader uses your existing Artsobservasjoner web session. If the site id
cannot be resolved, open the web form once and select a site, then try again.

## Adding new uploaders

Upload targets are registered in `utils/artsobs_uploaders.py`. Add a new class
with a unique `key`, `label`, and `login_url`, and implement `upload(...)`.

See the existing `ArtsobsMobileUploader` and `ArtsobsWebUploader` classes for
examples.

## After upload

- MycoLog stores the Artsobservasjoner sighting id in the observation (`artsdata_id`).
- The Observations table shows an **Artsobs** link that opens the uploaded sighting.

## See also

- [Database structure](docs/database-structure.md)
- [Taxonomy integration](docs/taxonomy-integration.md)
- [Field photography](docs/field-photography.md)
- [Microscopy workflow](docs/microscopy-workflow.md)
- [Spore measurements](docs/spore-measurements.md)
- [Integration notes](utils/MYCO_LOG_INTEGRATION.md)
