# CarbonAgent Rebrand & Theme Plan

## Goal
Rebrand the project from its current identity to **CarbonAgent** and redesign the interface to match the colour scheme of [Corporate Carbon](https://www.corporatecarbon.com.au/).

## Reference palette
Extracted from the Corporate Carbon logo:
- **Brand red**: `#C61A1D` / `#CE1B1E` (primary accent)
- **Black**: `#0A0A0A` / `#000000` (dark text, dark theme surfaces)
- **White / paper**: `#FFFFFF` / `#FAFAFA` (light theme backgrounds)
- **Neutral greys**: `#E5E5E5`, `#B0B0B0`, `#6B6B6B`

## Outcomes
1. Backend white-label defaults read "CarbonAgent" and use the red brand colour.
2. Frontend default palette and built-in themes reflect a clean, professional carbon/red scheme.
3. PWA manifest, package metadata, and README are updated.

## Tasks
1. Update backend white-label defaults (`src/white_label.py`) and `.env.example`.
2. Add a CarbonAgent frontend colour theme to `static/js/theme.js` and update CSS defaults in `static/style.css`.
3. Update `static/manifest.json`, `package.json`, and `README.md`.
4. Verify the app still boots and the new branding is visible.
