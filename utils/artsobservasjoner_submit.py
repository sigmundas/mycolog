"""
Artsobservasjoner Observation Submission Script

This script provides two approaches for submitting observations:
1. Cookie-based authentication (reusing browser session)
2. OAuth authentication (official API approach)
"""

import requests
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any
import base64


class ArtsObservasjonerClient:
    """Client for submitting observations to Artsobservasjoner"""
    
    # Mobile site endpoints (cookie-based)
    MOBILE_BASE_URL = "https://mobil.artsobservasjoner.no"
    
    # Official API endpoints (OAuth-based)
    API_BASE_URL = "https://api.artsobservasjoner.no/v1"
    API_TEST_URL = "https://apitest.artsobservasjoner.no/v1"
    
    def __init__(self, use_api: bool = False, api_test: bool = False):
        """
        Initialize the client
        
        Args:
            use_api: If True, use official API (requires OAuth). If False, use mobile site (requires cookies)
            api_test: If True and use_api=True, use test API endpoint
        """
        self.session = requests.Session()
        self.use_api = use_api
        
        if use_api:
            self.base_url = self.API_TEST_URL if api_test else self.API_BASE_URL
        else:
            self.base_url = self.MOBILE_BASE_URL
    
    # ========== APPROACH 1: Cookie-based (Mobile Site) ==========
    
    def set_cookies_from_browser(self, cookies_dict: Dict[str, str]):
        """
        Set cookies from your browser session
        
        Args:
            cookies_dict: Dictionary of cookie names and values
                         e.g., {'__Host-bff': 'chunks-2', '__Host-bffC1': '...', '__Host-bffC2': '...'}
        """
        for name, value in cookies_dict.items():
            self.session.cookies.set(name, value, domain='mobil.artsobservasjoner.no')
    
    def submit_observation_mobile(
        self,
        taxon_id: int,
        latitude: float,
        longitude: float,
        observed_datetime: datetime | str,
        image_path: Optional[str] = None,
        image_paths: Optional[list[str]] = None,
        site_id: Optional[int] = None,
        site_name: Optional[str] = None,
        count: int = 1,
        comment: Optional[str] = None,
        accuracy_meters: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Submit an observation using mobile site API (requires cookies)
        
        Args:
            taxon_id: Species ID from Artsdatabanken
            latitude: Observation latitude (WGS84)
            longitude: Observation longitude (WGS84)
            observed_datetime: When the observation was made (datetime or ISO string)
            image_path: Optional path to image file
            image_paths: Optional list of image paths
            site_id: Optional site ID (uses last used site if not provided)
            site_name: Optional site name to create a new site when site_id is not set
            count: Number of individuals observed
            comment: Optional observation comment
            accuracy_meters: GPS accuracy in meters
            
        Returns:
            Response from API containing observation ID
        """
        sighting_id, result = self.create_sighting_mobile(
            taxon_id=taxon_id,
            latitude=latitude,
            longitude=longitude,
            observed_datetime=observed_datetime,
            site_id=site_id,
            site_name=site_name,
            count=count,
            comment=comment,
            accuracy_meters=accuracy_meters,
        )
        
        # Upload image(s) if provided
        paths = []
        if image_paths:
            paths.extend([p for p in image_paths if p])
        elif image_path:
            paths.append(image_path)
        for path in paths:
            self._upload_image_mobile(sighting_id, path)

        return result if result is not None else {}

    def create_sighting_mobile(
        self,
        taxon_id: int,
        latitude: float,
        longitude: float,
        observed_datetime: datetime | str,
        site_id: Optional[int] = None,
        site_name: Optional[str] = None,
        count: int = 1,
        comment: Optional[str] = None,
        accuracy_meters: Optional[int] = None,
    ) -> tuple[int, Dict[str, Any] | None]:
        """Create a sighting on the mobile site and return (sighting_id, response)."""
        resolved_site_id = site_id
        new_site_info = None
        if resolved_site_id is None:
            resolved_site_id = self._get_last_used_site_id()
        if not resolved_site_id:
            site_label = (site_name or "").strip()
            if not site_label:
                site_label = f"MycoLog {latitude:.5f}, {longitude:.5f}"
            resolved_site_id = 0
            new_site_info = {
                "siteName": site_label,
                "longitude": longitude,
                "latitude": latitude,
                "isPolygon": False,
                "polygonCoordinates": None,
                "accuracy": accuracy_meters or 25,
            }

        observation = {
            "taxonId": taxon_id,
            "latitude": latitude,
            "longitude": longitude,
            "siteId": resolved_site_id,
            "startDate": self._format_start_date(observed_datetime),
            "startTime": self._format_start_time(observed_datetime),
            "quantity": count if count else None,
            "comment": comment or "",
        }
        if new_site_info:
            observation["newSiteInfo"] = new_site_info

        headers = {
            'Content-Type': 'application/json',
            'X-Csrf': '1',
            'Accept': 'application/json',
            'Referer': f'{self.MOBILE_BASE_URL}/contribute/submit-sightings'
        }

        url = f"{self.base_url}/core/Sightings"
        response = self.session.post(url, json=observation, headers=headers)
        if not response.ok:
            raise RuntimeError(
                f"Observation upload failed ({response.status_code}): {response.text}"
            )

        try:
            result = response.json()
        except ValueError:
            result = None

        sighting_id = self._extract_sighting_id(result)
        if not sighting_id:
            payload_preview = response.text.strip()
            if payload_preview:
                payload_preview = payload_preview[:1000]
            raise RuntimeError(
                "Observation upload did not return a sighting ID. "
                f"Response: {payload_preview or result}"
            )

        print(f"✓ Observation created with ID: {sighting_id}")
        return sighting_id, result

    def upload_image_mobile(self, sighting_id: int, image_path: str, license_code: str = "CC_BY_4"):
        """Public wrapper for uploading a single image to a sighting."""
        return self._upload_image_mobile(sighting_id, image_path, license_code=license_code)


    def _upload_image_mobile(self, sighting_id: int, image_path: str, license_code: str = "CC_BY_4"):
        """Upload an image to an existing observation"""
        
        image_file = Path(image_path)
        if not image_file.exists():
            raise FileNotFoundError(f"Image not found: {image_path}")
        
        # Prepare multipart upload (matches mobile UI)
        with open(image_path, 'rb') as handle:
            files = {
                'MediaFiles[0].File': (image_file.name, handle, 'image/jpeg')
            }
            data = {
                "sightingId": str(sighting_id),
                "MediaFiles[0].ImageLicense": license_code,
            }

            headers = {
                'X-Csrf': '1',
                'Referer': f'{self.MOBILE_BASE_URL}/contribute/submit-sightings'
            }

            url = f"{self.base_url}/core/MediaFiles/UploadImages?sightingId={sighting_id}"
            response = self.session.post(url, data=data, files=files, headers=headers)
            if not response.ok:
                raise RuntimeError(
                    f"Image upload failed ({response.status_code}): {response.text}"
                )
            
            print(f"✓ Image uploaded successfully")
            
            return response.json()

    @staticmethod
    def _extract_sighting_id(result: Any) -> int | None:
        if isinstance(result, dict):
            for key in ("Id", "id", "SightingId", "sightingId"):
                if key in result:
                    try:
                        return int(result[key])
                    except (TypeError, ValueError):
                        return None
            nested = result.get("data") or result.get("sighting") or result.get("Sighting")
            if isinstance(nested, dict):
                for key in ("Id", "id", "SightingId", "sightingId"):
                    if key in nested:
                        try:
                            return int(nested[key])
                        except (TypeError, ValueError):
                            return None
        if isinstance(result, list):
            for item in result:
                if isinstance(item, dict):
                    found = ArtsObservasjonerClient._extract_sighting_id(item)
                    if found:
                        return found
        return None

    def _format_observed_datetime(self, value: datetime | str) -> str:
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, str):
            try:
                return datetime.fromisoformat(value).isoformat()
            except ValueError:
                return value
        return str(value)

    def _format_start_date(self, value: datetime | str) -> str:
        if isinstance(value, datetime):
            return f"{value.date().isoformat()}T00:00:00.000Z"
        if isinstance(value, str):
            try:
                parsed = datetime.fromisoformat(value)
                return f"{parsed.date().isoformat()}T00:00:00.000Z"
            except ValueError:
                try:
                    parsed = datetime.strptime(value, "%d.%m.%Y %H:%M")
                    return f"{parsed.date().isoformat()}T00:00:00.000Z"
                except ValueError:
                    try:
                        parsed = datetime.strptime(value, "%d.%m.%Y %H:%M:%S")
                        return f"{parsed.date().isoformat()}T00:00:00.000Z"
                    except ValueError:
                        pass
                date_part = value.split("T")[0].split(" ")[0]
                return f"{date_part}T00:00:00.000Z"
        return str(value)

    def _format_start_time(self, value: datetime | str) -> str | None:
        if isinstance(value, datetime):
            return value.strftime("%H:%M")
        if isinstance(value, str):
            try:
                return datetime.fromisoformat(value).strftime("%H:%M")
            except ValueError:
                try:
                    return datetime.strptime(value, "%d.%m.%Y %H:%M").strftime("%H:%M")
                except ValueError:
                    try:
                        return datetime.strptime(value, "%d.%m.%Y %H:%M:%S").strftime("%H:%M")
                    except ValueError:
                        pass
                if " " in value:
                    time_part = value.split(" ", 1)[1]
                    return time_part.split(":")[0] + ":" + time_part.split(":")[1]
        return None

    def _get_last_used_site_id(self) -> Optional[int]:
        headers = {
            'Accept': 'application/json',
            'X-Csrf': '1',
        }
        url = f"{self.base_url}/core/Sites/ByUser/LastUsed?top=1"
        response = self.session.get(url, headers=headers, timeout=10)
        if not response.ok:
            return None
        try:
            data = response.json()
        except Exception:
            return None
        if isinstance(data, list) and data:
            site_id = data[0].get("Id") or data[0].get("SiteId")
            try:
                return int(site_id)
            except (TypeError, ValueError):
                return None
        if isinstance(data, dict):
            site_id = data.get("Id") or data.get("SiteId")
            try:
                return int(site_id)
            except (TypeError, ValueError):
                return None
        return None
    
    # ========== APPROACH 2: OAuth API ==========
    
    def authenticate_oauth(
        self,
        client_id: str,
        client_secret: str,
        authorization_code: Optional[str] = None,
        access_token: Optional[str] = None
    ):
        """
        Authenticate using OAuth flow
        
        To get client_id and client_secret:
        - Contact Artsobservasjoner/Artsdatabanken to register your application
        
        Args:
            client_id: Your application's client ID
            client_secret: Your application's client secret
            authorization_code: Code from authorization step (if doing full OAuth)
            access_token: Previously obtained access token (to skip authorization)
        """
        if access_token:
            # Use existing token
            self.session.headers.update({
                'Authorization': f'Basic {access_token}'
            })
            return
        
        if not authorization_code:
            # Start OAuth flow
            auth_url = (
                f"{self.base_url}/authentication/authorize"
                f"?client_id={client_id}"
                f"&redirect_uri=YOUR_REDIRECT_URI"
                f"&state=RANDOM_STATE_STRING"
            )
            print(f"Visit this URL to authorize:\n{auth_url}")
            print("\nAfter authorization, you'll get a 'code' parameter in the redirect URL.")
            print("Pass that code to this function as 'authorization_code'")
            return
        
        # Exchange authorization code for access token
        url = (
            f"{self.base_url}/authentication/access_token"
            f"?client_id={client_id}"
            f"&client_secret={client_secret}"
            f"&code={authorization_code}"
            f"&state=RANDOM_STATE_STRING"
        )
        
        response = requests.get(url)
        response.raise_for_status()
        
        token_data = response.json()
        access_token = token_data['access_token']
        scheme = token_data['scheme']
        
        self.session.headers.update({
            'Authorization': f'{scheme} {access_token}'
        })
        
        print(f"✓ Authenticated as: {token_data['name']}")
        print(f"Token expires in: {token_data['expires_in']} seconds")
        
        return token_data
    
    def submit_observation_api(
        self,
        taxon_id: int,
        latitude: float,
        longitude: float,
        observed_datetime: datetime,
        image_path: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Submit observation using official API (requires OAuth authentication)
        
        Similar to submit_observation_mobile but uses official API endpoints
        """
        # This would use the official v1/sightings endpoint
        # The exact structure depends on the API specification
        
        observation = {
            "TaxonId": taxon_id,
            "Latitude": latitude,
            "Longitude": longitude,
            "ObservationDateTime": observed_datetime.isoformat(),
            **kwargs
        }
        
        url = f"{self.base_url}/sightings"
        response = self.session.post(url, json=observation)
        response.raise_for_status()
        
        return response.json()


class ArtsObservasjonerWebClient:
    """Client for submitting observations via www.artsobservasjoner.no (form post)."""

    BASE_URL = "https://www.artsobservasjoner.no"

    def __init__(self):
        self.session = requests.Session()

    def set_cookies_from_browser(self, cookies_dict: Dict[str, str]):
        for name, value in cookies_dict.items():
            self.session.cookies.set(name, value, domain=".artsobservasjoner.no")

    def submit_observation_web(
        self,
        taxon_id: int,
        observed_datetime: datetime | str,
        site_id: Optional[int],
        site_name: Optional[str],
        count: int,
        habitat: Optional[str],
        notes: Optional[str],
        progress_cb: Optional[callable] = None,
    ) -> Dict[str, Any]:
        token = self._get_request_verification_token()
        if progress_cb:
            progress_cb("Validating date/time...", 1, 3)
        self._validate_start_datetime(observed_datetime)
        if progress_cb:
            progress_cb("Validating taxon...", 2, 3)
        self._validate_taxon(taxon_id)

        if not site_id:
            site_id, site_name = self._resolve_site()
            if not site_id:
                raise RuntimeError(
                    "No site selected. Please select a site once in the Artsobservasjoner web form."
                )

        if progress_cb:
            progress_cb("Submitting observation...", 3, 3)
        payload = self._build_save_payload(
            token=token,
            taxon_id=taxon_id,
            observed_datetime=observed_datetime,
            site_id=site_id,
            site_name=site_name or "",
            count=count,
            habitat=habitat,
            notes=notes,
        )
        headers = {
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "X-Requested-With": "XMLHttpRequest",
            "Origin": self.BASE_URL,
            "Referer": f"{self.BASE_URL}/SubmitSighting/Report",
        }
        url = f"{self.BASE_URL}/SubmitSighting/SaveSighting"
        response = self.session.post(url, data=payload, headers=headers)
        if not response.ok:
            raise RuntimeError(
                f"Observation upload failed ({response.status_code}): {response.text}"
            )
        sighting_id = self._extract_sighting_id(response.text)
        result: Dict[str, Any] = {"sighting_id": sighting_id}
        return result

    def _get_request_verification_token(self) -> str:
        url = f"{self.BASE_URL}/SubmitSighting/Report"
        response = self.session.get(url)
        if not response.ok:
            raise RuntimeError(
                f"Failed to load report form ({response.status_code}): {response.text}"
            )
        match = re.search(
            r'name="__RequestVerificationToken"[^>]*value="([^"]+)"',
            response.text
        )
        if not match:
            raise RuntimeError("Could not find __RequestVerificationToken on report form.")
        return match.group(1)

    def _validate_start_datetime(self, observed_datetime: datetime | str) -> None:
        date_str = self._format_date_ddmmyyyy(observed_datetime)
        data = {
            "SightingViewModel.TemporarySighting.Sighting.StartDate": date_str,
            "SightingViewModel.TemporarySighting.Sighting.StartTime": "",
            "SightingViewModel.TemporarySighting.Sighting.EndDate": date_str,
            "SightingViewModel.TemporarySighting.Sighting.EndTime": "",
        }
        headers = {
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "X-Requested-With": "XMLHttpRequest",
            "Origin": self.BASE_URL,
            "Referer": f"{self.BASE_URL}/SubmitSighting/Report",
        }
        url = f"{self.BASE_URL}/SightingValidation/ValidateStartDateTime"
        response = self.session.post(url, data=data, headers=headers)
        if not response.ok:
            raise RuntimeError(
                f"Start date validation failed ({response.status_code}): {response.text}"
            )

    def _validate_taxon(self, taxon_id: int) -> None:
        data = {
            "SightingViewModel.TemporarySighting.Sighting.Taxon": str(taxon_id)
        }
        headers = {
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "X-Requested-With": "XMLHttpRequest",
            "Origin": self.BASE_URL,
            "Referer": f"{self.BASE_URL}/SubmitSighting/Report",
        }
        url = f"{self.BASE_URL}/SightingValidation/ValidateTaxonReportable"
        response = self.session.post(url, data=data, headers=headers)
        if not response.ok:
            raise RuntimeError(
                f"Taxon validation failed ({response.status_code}): {response.text}"
            )

    def _resolve_site(self) -> tuple[Optional[int], Optional[str]]:
        headers = {
            "Content-Type": "application/json; charset=UTF-8",
            "X-Requested-With": "XMLHttpRequest",
            "Origin": self.BASE_URL,
            "Referer": f"{self.BASE_URL}/SubmitSighting/Report",
        }
        url = f"{self.BASE_URL}/Site/GetUserSites"
        response = self.session.post(url, data="null", headers=headers)
        if not response.ok:
            return None, None
        try:
            data = response.json()
        except Exception:
            return None, None
        if isinstance(data, list) and data:
            site = data[0]
            site_id = site.get("Id") or site.get("id")
            name = site.get("Name") or site.get("name")
            try:
                return int(site_id), name
            except (TypeError, ValueError):
                return None, None
        return None, None

    def _build_save_payload(
        self,
        token: str,
        taxon_id: int,
        observed_datetime: datetime | str,
        site_id: int,
        site_name: str,
        count: int,
        habitat: Optional[str],
        notes: Optional[str],
    ) -> Dict[str, str]:
        date_str = self._format_date_ddmmyyyy(observed_datetime)
        time_str = self._format_time_hhmm(observed_datetime)
        payload = {
            "__RequestVerificationToken": token,
            "SightingViewModel.CopyFromSightingId": "0",
            "SightingViewModel.ExternalMetadataId": "",
            "SightingViewModel.TemporarySighting.Id": "0",
            "SightingViewModel.EditableProperties.Taxon.IsEditable": "True",
            "_ignore_SightingViewModel.TemporarySighting.Sighting.Taxon": str(taxon_id),
            "SightingViewModel.TemporarySighting.Sighting.Taxon": str(taxon_id),
            "SightingViewModel.TemporarySighting.Sighting.Taxon_autoselect": "false",
            "SightingViewModel.TemporarySighting.Sighting.UnsureDetermination": "false",
            "SightingViewModel.TemporarySighting.Sighting.Unspontaneous": "false",
            "SightingViewModel.TemporarySighting.Sighting.StartDate": date_str,
            "SightingViewModel.TemporarySighting.Sighting.StartTime": time_str or "",
            "SightingViewModel.TemporarySighting.Sighting.EndDate": date_str,
            "SightingViewModel.TemporarySighting.Sighting.EndTime": "",
            "SightingViewModel.TemporarySighting.Sighting.Quantity": str(count),
            "SightingViewModel.TemporarySighting.Sighting.Unit": "0",
            "SightingViewModel.TemporarySighting.Sighting.PublicComment.Comment": notes or "",
            "SightingViewModel.TemporarySighting.Sighting.PrivateComment.Comment": "",
            "SightingViewModel.TemporarySighting.Sighting.BiotopeDescription.Id": "0",
            "SightingViewModel.TemporarySighting.Sighting.BiotopeDescription.Description": habitat or "",
            "SightingViewModel.SelectedSite.Id": str(site_id),
            "selectedSiteName": site_name,
            "selectedSiteIsPrivate": "true",
            "selectedSiteIsFavorite": "false",
            "selectedSiteSpeciesGroupId": "0",
            "SightingViewModel.IsNewSite": "false",
            "SightingViewModel.NewSite.NewSiteCoordinate.Accuracy": "0",
            "currentSpeciesGroupId": "4",
        }
        return payload

    @staticmethod
    def _extract_sighting_id(text: str) -> Optional[int]:
        if not text:
            return None
        patterns = [
            r"data-sighting-id=[\"'](\d+)[\"']",
            r"SightingId\\D+(\\d+)",
        ]
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                try:
                    return int(match.group(1))
                except (TypeError, ValueError):
                    return None
        return None

    @staticmethod
    def _format_date_ddmmyyyy(value: datetime | str) -> str:
        if isinstance(value, datetime):
            return value.strftime("%d.%m.%Y")
        if isinstance(value, str):
            try:
                parsed = datetime.fromisoformat(value)
                return parsed.strftime("%d.%m.%Y")
            except ValueError:
                try:
                    parsed = datetime.strptime(value, "%Y-%m-%d %H:%M")
                    return parsed.strftime("%d.%m.%Y")
                except ValueError:
                    try:
                        parsed = datetime.strptime(value, "%Y-%m-%d")
                        return parsed.strftime("%d.%m.%Y")
                    except ValueError:
                        return value.split(" ")[0]
        return str(value)

    @staticmethod
    def _format_time_hhmm(value: datetime | str) -> str | None:
        if isinstance(value, datetime):
            return value.strftime("%H:%M")
        if isinstance(value, str):
            try:
                parsed = datetime.fromisoformat(value)
                return parsed.strftime("%H:%M")
            except ValueError:
                try:
                    parsed = datetime.strptime(value, "%Y-%m-%d %H:%M")
                    return parsed.strftime("%H:%M")
                except ValueError:
                    pass
                if " " in value:
                    time_part = value.split(" ", 1)[1]
                    return ":".join(time_part.split(":")[:2])
        return None


# ========== HELPER FUNCTIONS ==========

def extract_cookies_from_browser():
    """
    Helper to extract cookies from your browser
    
    FIREFOX:
    1. Open Firefox
    2. Visit https://mobil.artsobservasjoner.no (logged in)
    3. Press F12 to open Developer Tools
    4. Go to Storage tab -> Cookies
    5. Copy the values for __Host-bff, __Host-bffC1, __Host-bffC2
    
    CHROME:
    1. Open Chrome
    2. Visit https://mobil.artsobservasjoner.no (logged in)
    3. Press F12 to open Developer Tools
    4. Go to Application tab -> Cookies
    5. Copy the values
    
    Returns a dict like:
    {
        '__Host-bff': 'chunks-2',
        '__Host-bffC1': 'CfDJ8H96...',
        '__Host-bffC2': 'CwjI1fy0...'
    }
    """
    print("To extract cookies from your browser:")
    print("1. Visit https://mobil.artsobservasjoner.no (while logged in)")
    print("2. Open Developer Tools (F12)")
    print("3. Firefox: Storage -> Cookies | Chrome: Application -> Cookies")
    print("4. Copy the values for __Host-bff, __Host-bffC1, __Host-bffC2")
    print("\nReturn them in this format:")
    print("""
    cookies = {
        '__Host-bff': 'chunks-2',
        '__Host-bffC1': 'YOUR_LONG_VALUE_HERE...',
        '__Host-bffC2': 'YOUR_LONG_VALUE_HERE...'
    }
    """)


# ========== USAGE EXAMPLES ==========

def example_cookie_based():
    """Example: Using cookie-based authentication (easiest for personal use)"""
    
    # 1. Extract cookies from your browser (see extract_cookies_from_browser())
    cookies = {
        '__Host-bff': 'chunks-2',
        '__Host-bffC1': 'YOUR_VALUE_HERE',  # Long encrypted value from browser
        '__Host-bffC2': 'YOUR_VALUE_HERE',  # Long encrypted value from browser
    }
    
    # 2. Create client and set cookies
    client = ArtsObservasjonerClient(use_api=False)
    client.set_cookies_from_browser(cookies)
    
    # 3. Submit observation
    observation = client.submit_observation_mobile(
        taxon_id=123456,  # Get this from species identification
        latitude=59.9139,  # Oslo coordinates
        longitude=10.7522,
        observed_datetime=datetime.now(),
        image_path="/path/to/mushroom_photo.jpg",
        count=3,
        comment="Found in moss near oak tree",
        accuracy_meters=5
    )
    
    print(f"Observation ID: {observation['Id']}")
    print(f"View at: https://mobil.artsobservasjoner.no/sighting/{observation['Id']}")


def example_oauth_based():
    """Example: Using OAuth authentication (recommended for apps)"""
    
    # 1. Register your app with Artsobservasjoner to get credentials
    CLIENT_ID = "your_client_id"
    CLIENT_SECRET = "your_client_secret"
    
    # 2. Create client and authenticate
    client = ArtsObservasjonerClient(use_api=True, api_test=True)
    
    # First time: Get authorization URL
    # client.authenticate_oauth(CLIENT_ID, CLIENT_SECRET)
    # User visits URL, authorizes, you get code
    
    # Then: Exchange code for token
    # token_data = client.authenticate_oauth(
    #     CLIENT_ID, 
    #     CLIENT_SECRET, 
    #     authorization_code="CODE_FROM_REDIRECT"
    # )
    
    # Or: Use previously obtained token
    client.authenticate_oauth(
        CLIENT_ID,
        CLIENT_SECRET,
        access_token="YOUR_SAVED_TOKEN"
    )
    
    # 3. Submit observation
    observation = client.submit_observation_api(
        taxon_id=123456,
        latitude=59.9139,
        longitude=10.7522,
        observed_datetime=datetime.now(),
        image_path="/path/to/photo.jpg"
    )


if __name__ == "__main__":
    print("Artsobservasjoner Observation Submission Tool\n")
    print("Choose your approach:")
    print("1. Cookie-based (easier, for personal use)")
    print("2. OAuth-based (better, for apps)")
    print("\nSee example_cookie_based() and example_oauth_based() for usage")
    print("\nTo extract cookies, run: extract_cookies_from_browser()")
