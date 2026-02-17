"""Artsobservasjoner login and cookie capture for MycoLog."""

import json
import os
import re
import sys
from pathlib import Path
import requests
from platformdirs import user_data_dir
from typing import Dict, Optional, Callable


def _prompt_web_credentials(parent=None) -> tuple[Optional[str], Optional[str]]:
    """Show a Qt dialog for Artsobservasjoner web credentials."""
    from PySide6.QtWidgets import (
        QDialog,
        QDialogButtonBox,
        QFormLayout,
        QLabel,
        QLineEdit,
        QMessageBox,
        QVBoxLayout,
    )

    dialog = QDialog(parent)
    dialog.setWindowTitle("Log in to Artsobservasjoner (web)")
    dialog.setModal(True)
    dialog.setMinimumWidth(420)

    layout = QVBoxLayout(dialog)
    layout.addWidget(QLabel("Enter your Artsobservasjoner email and password:"))

    form = QFormLayout()
    username_edit = QLineEdit()
    username_edit.setPlaceholderText("Email")
    password_edit = QLineEdit()
    password_edit.setPlaceholderText("Password")
    password_edit.setEchoMode(QLineEdit.Password)
    form.addRow("Email:", username_edit)
    form.addRow("Password:", password_edit)
    layout.addLayout(form)

    buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
    layout.addWidget(buttons)

    def _accept_if_valid():
        if not username_edit.text().strip() or not password_edit.text():
            QMessageBox.warning(
                dialog,
                "Missing Information",
                "Please enter both email and password.",
            )
            return
        dialog.accept()

    buttons.accepted.connect(_accept_if_valid)
    buttons.rejected.connect(dialog.reject)
    username_edit.returnPressed.connect(_accept_if_valid)
    password_edit.returnPressed.connect(_accept_if_valid)
    username_edit.setFocus()

    if dialog.exec() != QDialog.Accepted:
        return None, None

    return username_edit.text().strip(), password_edit.text()


class ArtsObservasjonerWebLogin:
    """Handles programmatic login to www.artsobservasjoner.no."""

    BASE_URL = "https://www.artsobservasjoner.no"

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (X11; Linux x86_64; rv:147.0) "
                    "Gecko/20100101 Firefox/147.0"
                ),
                "Accept-Language": "en-US,en;q=0.9",
            }
        )

    def get_csrf_token(self) -> Optional[str]:
        """Fetch /Logon and extract __RequestVerificationToken."""
        response = self.session.get(f"{self.BASE_URL}/Logon", timeout=20)
        response.raise_for_status()

        match = re.search(
            r'name="__RequestVerificationToken"[^>]+value="([^"]+)"',
            response.text,
        )
        if match:
            return match.group(1)

        return self.session.cookies.get("__RequestVerificationToken")

    def login(self, username: str, password: str) -> bool:
        """Authenticate with username/password."""
        csrf_token = self.get_csrf_token()
        if not csrf_token:
            raise RuntimeError("Failed to get CSRF token from Artsobservasjoner.")

        login_data = {
            "__RequestVerificationToken": csrf_token,
            "AuthenticationViewModel.UserName": username,
            "AuthenticationViewModel.ReturnUrl": "",
            "AuthenticationViewModel.Password": password,
            "AuthenticationViewModel.RememberMe": "false",
            "Shared_LogOn": "Logg inn",
        }

        response = self.session.post(
            f"{self.BASE_URL}/LogOn",
            data=login_data,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Referer": f"{self.BASE_URL}/Logon",
            },
            allow_redirects=True,
            timeout=20,
        )
        response.raise_for_status()

        if ".ASPXAUTHNO" not in self.session.cookies:
            return False
        return self.check_auth()

    def check_auth(self) -> bool:
        """Check if session can access MyPages without being redirected to login."""
        response = self.session.get(
            f"{self.BASE_URL}/User/MyPages",
            allow_redirects=True,
            timeout=10,
        )
        if response.status_code != 200:
            return False
        url = (response.url or "").lower()
        return "/logon" not in url and "/account/login" not in url

    def get_cookies_dict(self) -> Dict[str, str]:
        return requests.utils.dict_from_cookiejar(self.session.cookies)


class ArtsObservasjonerAuthWidget:
    """
    PySide6 widget for Artsobservasjoner login
    
    Usage in MycoLog:
    1. Show this widget in a dialog when user needs to authenticate
    2. User logs in through the embedded browser
    3. Widget automatically captures cookies
    4. Save cookies for future use
    """
    
    def __init__(
        self,
        on_login_success: Optional[Callable] = None,
        parent=None,
        login_url: Optional[str] = None,
        required_cookies: Optional[list[str]] = None,
    ):
        """
        Args:
            on_login_success: Callback function called with cookies dict when login succeeds
        """
        os.environ.setdefault("QTWEBENGINE_DISABLE_GPU", "1")
        os.environ.setdefault("QT_QUICK_BACKEND", "software")
        os.environ.setdefault("LIBGL_ALWAYS_SOFTWARE", "1")
        os.environ.setdefault(
            "QTWEBENGINE_CHROMIUM_FLAGS",
            "--disable-gpu --disable-software-rasterizer"
        )
        if sys.platform.startswith("linux"):
            # Avoid loading libproxy-based GIO module in mixed snap/system setups.
            os.environ.setdefault("GIO_USE_PROXY_RESOLVER", "0")
        from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QPushButton, QSizePolicy
        from PySide6.QtWebEngineWidgets import QWebEngineView
        from PySide6.QtWebEngineCore import QWebEngineProfile
        from PySide6.QtCore import QUrl
        
        self.widget = QWidget(parent)
        self.on_login_success = on_login_success
        
        # Create layout
        layout = QVBoxLayout()
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)
        
        # Instructions
        label = QLabel("Log in to Artsobservasjoner to continue:")
        layout.addWidget(label)
        
        # Embedded browser
        self.web_view = QWebEngineView()
        self.web_view.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.profile = QWebEngineProfile.defaultProfile()
        self.cookie_store = self.profile.cookieStore()
        
        # Monitor cookies
        self.cookies = {}
        if required_cookies is None:
            if login_url and "www.artsobservasjoner.no" in login_url:
                required_cookies = [".ASPXAUTHNO"]
            else:
                required_cookies = ["__Host-bff", "__Host-bffC1", "__Host-bffC2"]
        self.required_cookies = required_cookies
        self._login_saved = False
        self.cookie_store.cookieAdded.connect(self._on_cookie_added)
        
        # Load the Artsobservasjoner login entry point.
        if not login_url:
            login_url = "https://mobil.artsobservasjoner.no/bff/login?returnUrl=/my-page"
        self.web_view.setUrl(QUrl(login_url))
        layout.addWidget(self.web_view)
        
        # Done button
        self.done_button = QPushButton("Done - Save Login")
        self.done_button.clicked.connect(self._on_done)
        self.done_button.setEnabled(False)  # Enable once we have cookies
        layout.addWidget(self.done_button)
        
        self.widget.setLayout(layout)
        self.widget.setWindowTitle("Log in to Artsobservasjoner")
        self.widget.setMinimumSize(700, 540)
        self.widget.resize(860, 640)
    
    def _on_cookie_added(self, cookie):
        """Called when browser receives a cookie"""
        name = bytes(cookie.name()).decode('utf-8')
        value = bytes(cookie.value()).decode('utf-8')
        domain = cookie.domain()
        
        # Store cookies from artsobservasjoner.no
        if 'artsobservasjoner.no' in domain:
            self.cookies[name] = value
            
            # Check if we have all required cookies
            if all(k in self.cookies for k in self.required_cookies):
                self.done_button.setEnabled(True)
                self.done_button.setText(f"Logged in - Click to Save ({len(self.cookies)} cookies)")
                if not self._login_saved and self.on_login_success:
                    self._login_saved = True
                    self.on_login_success(self.cookies)
                    self.widget.close()
    
    def _on_done(self):
        """User clicked done - save cookies and close"""
        if self.on_login_success:
            self.on_login_success(self.cookies)
        self.widget.close()
    
    def show(self):
        """Show the login widget"""
        self.widget.show()
        return self.widget
    
    def get_cookies(self) -> Dict[str, str]:
        """Get captured cookies"""
        return self.cookies


class ArtsObservasjonerAuth:
    """
    Unified authentication manager
    Tries multiple approaches and caches cookies
    """
    
    def __init__(self, cookies_file: Optional[Path] = None):
        """
        Args:
            cookies_file: Where to cache cookies (default: ~/.myco_log/artsobservasjoner_cookies.json)
        """
        if cookies_file is None:
            cookies_file = (
                Path(user_data_dir("MycoLog", appauthor=False, roaming=True))
                / "artsobservasjoner_cookies.json"
            )
        self.cookies_file = Path(cookies_file)
        self._migrate_legacy_cookies()
        self.cookies_file.parent.mkdir(parents=True, exist_ok=True)

    def _migrate_legacy_cookies(self) -> None:
        legacy_file = Path.home() / ".myco_log" / "artsobservasjoner_cookies.json"
        if not legacy_file.exists() or self.cookies_file.exists():
            return
        try:
            self.cookies_file.parent.mkdir(parents=True, exist_ok=True)
            legacy_file.replace(self.cookies_file)
        except Exception:
            return
    
    def load_cookies(self) -> Optional[Dict[str, str]]:
        """Load cached cookies if they exist"""
        if self.cookies_file.exists():
            with open(self.cookies_file) as f:
                cookies = json.load(f)
                print(f"✓ Loaded {len(cookies)} cached cookies")
                return cookies
        return None
    
    def save_cookies(self, cookies: Dict[str, str]):
        """Save cookies to cache"""
        with open(self.cookies_file, 'w') as f:
            json.dump(cookies, f, indent=2)
        print(f"✓ Saved {len(cookies)} cookies to {self.cookies_file}")
    
    def login_with_gui(self, callback: Optional[Callable] = None) -> Dict[str, str]:
        """
        Show PyQt login dialog (best for MycoLog)
        
        Args:
            callback: Function to call when login succeeds
        """
        def on_success(cookies):
            self.save_cookies(cookies)
            if callback:
                callback(cookies)
        
        auth_widget = ArtsObservasjonerAuthWidget(on_login_success=on_success)
        auth_widget.show()
        return auth_widget.get_cookies()

    def login_web_with_gui(self, parent=None, callback: Optional[Callable] = None) -> Optional[Dict[str, str]]:
        """
        Prompt for web credentials and authenticate against www.artsobservasjoner.no.

        Returns:
            Cookie dict on success, None if user cancelled.
        """
        username, password = _prompt_web_credentials(parent=parent)
        if username is None:
            return None

        web_auth = ArtsObservasjonerWebLogin()
        success = web_auth.login(username=username, password=password)
        if not success:
            raise RuntimeError("Login failed. Please check your email and password.")

        cookies = web_auth.get_cookies_dict()
        if not cookies:
            raise RuntimeError("Login succeeded but no cookies were returned.")

        if callback:
            callback(cookies)
        else:
            self.save_cookies(cookies)
        return cookies
    
    def get_valid_cookies(self, target: str = "mobile") -> Optional[Dict[str, str]]:
        """
        Get valid cookies, using cache if available
        
        Returns None if no valid cookies found
        """
        cookies = self.load_cookies()
        
        if cookies and self._validate_cookies(cookies, target=target):
            return cookies
        
        return None
    
    def _validate_cookies(self, cookies: Dict[str, str], target: str = "mobile") -> bool:
        """
        Test if cookies are still valid
        """
        target_key = (target or "mobile").lower()
        if target_key == "web":
            return self._validate_web_cookies(cookies)
        return self._validate_mobile_cookies(cookies)

    def _validate_mobile_cookies(self, cookies: Dict[str, str]) -> bool:
        session = requests.Session()
        for name, value in cookies.items():
            session.cookies.set(name, value, domain='mobil.artsobservasjoner.no')
        
        try:
            # Try a simple authenticated endpoint
            response = session.get(
                'https://mobil.artsobservasjoner.no/core/Sites/ByUser/LastUsed?top=1',
                headers={'X-Csrf': '1'},
                timeout=5
            )
            return response.status_code == 200
        except requests.RequestException:
            return False

    def _validate_web_cookies(self, cookies: Dict[str, str]) -> bool:
        if ".ASPXAUTHNO" not in cookies:
            return False

        session = requests.Session()
        for name, value in cookies.items():
            session.cookies.set(name, value, domain=".artsobservasjoner.no")

        try:
            response = session.get(
                "https://www.artsobservasjoner.no/User/MyPages",
                allow_redirects=True,
                timeout=8,
            )
        except requests.RequestException:
            return False

        if response.status_code != 200:
            return False
        url = (response.url or "").lower()
        return "/logon" not in url and "/account/login" not in url
