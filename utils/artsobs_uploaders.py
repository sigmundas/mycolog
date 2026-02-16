"""Uploader registry for Artsobservasjoner targets."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional, Protocol

from utils.artsobservasjoner_submit import ArtsObservasjonerClient, ArtsObservasjonerWebClient

ProgressCallback = Callable[[str, int, int], None]


@dataclass
class UploadResult:
    sighting_id: Optional[int]
    raw: dict | None


class ObservationUploader(Protocol):
    key: str
    label: str
    login_url: str

    def upload(
        self,
        observation: dict,
        image_paths: list[str],
        cookies: dict,
        progress_cb: Optional[ProgressCallback] = None,
    ) -> UploadResult:
        ...


class ArtsobsMobileUploader:
    key = "mobile"
    label = "Artsobservasjoner (mobile)"
    login_url = "https://mobil.artsobservasjoner.no/bff/login?returnUrl=/my-page"

    def upload(
        self,
        observation: dict,
        image_paths: list[str],
        cookies: dict,
        progress_cb: Optional[ProgressCallback] = None,
    ) -> UploadResult:
        client = ArtsObservasjonerClient(use_api=False)
        client.set_cookies_from_browser(cookies)

        submit_kwargs = dict(
            taxon_id=observation["taxon_id"],
            latitude=float(observation["latitude"]),
            longitude=float(observation["longitude"]),
            observed_datetime=observation["observed_datetime"],
            count=observation.get("count", 1),
            comment=observation.get("comment") or "",
            accuracy_meters=observation.get("accuracy_meters") or 25,
        )
        site_name = (observation.get("site_name") or "").strip()
        if site_name:
            submit_kwargs["site_name"] = site_name

        if hasattr(client, "create_sighting_mobile") and hasattr(client, "upload_image_mobile"):
            if progress_cb:
                progress_cb("Creating observation...", 1, len(image_paths) + 2)
            sighting_id, result = client.create_sighting_mobile(**submit_kwargs)

            for idx, path in enumerate(image_paths, start=1):
                if progress_cb:
                    progress_cb(
                        f"Uploading image {idx}/{len(image_paths)}...",
                        1 + idx,
                        len(image_paths) + 2
                    )
                client.upload_image_mobile(sighting_id, path)

            if progress_cb:
                progress_cb("Upload complete.", len(image_paths) + 2, len(image_paths) + 2)
            return UploadResult(sighting_id=sighting_id, raw=result)

        if progress_cb:
            progress_cb("Uploading observation...", 1, 1)
        result = client.submit_observation_mobile(
            **submit_kwargs,
            image_paths=image_paths,
        )
        sighting_id = ArtsObservasjonerClient._extract_sighting_id(result)
        return UploadResult(sighting_id=sighting_id, raw=result)


class ArtsobsWebUploader:
    key = "web"
    label = "Artsobservasjoner (web)"
    login_url = "https://www.artsobservasjoner.no/Account/Login?ReturnUrl=%2FSubmitSighting%2FReport"

    def upload(
        self,
        observation: dict,
        image_paths: list[str],
        cookies: dict,
        progress_cb: Optional[ProgressCallback] = None,
    ) -> UploadResult:
        client = ArtsObservasjonerWebClient()
        client.set_cookies_from_browser(cookies)
        result = client.submit_observation_web(
            taxon_id=observation["taxon_id"],
            observed_datetime=observation["observed_datetime"],
            site_id=observation.get("site_id"),
            site_name=observation.get("site_name"),
            count=observation.get("count", 1),
            habitat=observation.get("habitat"),
            notes=observation.get("notes"),
            progress_cb=progress_cb,
        )
        return UploadResult(sighting_id=result.get("sighting_id"), raw=result)


_UPLOADERS = {
    ArtsobsMobileUploader.key: ArtsobsMobileUploader(),
    ArtsobsWebUploader.key: ArtsobsWebUploader(),
}


def list_uploaders() -> list[ObservationUploader]:
    return list(_UPLOADERS.values())


def get_uploader(key: str | None) -> ObservationUploader | None:
    if not key:
        return _UPLOADERS.get(ArtsobsMobileUploader.key)
    return _UPLOADERS.get(key)
