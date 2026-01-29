# Translations

Source strings are extracted from the UI into `.ts` files using Qt Linguist tools.

Update extraction:
- PowerShell: `./tools/update_translations.ps1`
- Bash: `./tools/update_translations.sh`

Compile `.ts` to `.qm` with `lrelease` (or Qt Linguist).
