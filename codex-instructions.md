# Steam Library Cleaner (Python GUI) — Project Instructions

## Goal
Create a Python desktop application that:
- Lets the user add one or more **mount points** (directories).
- Scans those mount points for **Steam libraries** and lists installed games.
- Allows removing selected games (and associated Steam files) reliably, because Steam’s GUI uninstall is broken.

This app is **functional-first** (not beauty-first) but must support **dark/light mode**.

---

## Target OS / Environment
- Primary target: Linux (Ubuntu-like).  
- Python 3.10+.
- Must work without Steam running (but should detect and warn if Steam is running).

---

## Steam Library Detection (Linux)
A mount point may contain a Steam library in one of these common patterns:
- `<mount>/SteamLibrary`
- `<mount>/steamapps` (if the mount point itself is the library root)
- `<mount>/.steam/steam` or `~/.steam/steam` are NOT mount points, but scanning should still work if user adds them.

A Steam library root is defined as a directory containing:
- `steamapps/`
- and within it typically:
  - `steamapps/common/`
  - `steamapps/appmanifest_*.acf` files

### Installed Games Enumeration
For each library root:
1. Look in `steamapps/` for `appmanifest_*.acf`.
2. Parse each manifest to obtain:
   - `appid`
   - `name`
   - `installdir`
3. Compute the game install directory:
   - `<library_root>/steamapps/common/<installdir>`
4. Include a game in the list if:
   - manifest exists AND installdir exists (or show as “broken/missing” with a warning icon/text).

Manifest format notes:
- ACF is KeyValues-like. Implement a tolerant parser:
  - handles `"key"  "value"`
  - nested blocks exist but for this app we mainly need top-level `name`, `appid`, `installdir`.
  - ignore unknown keys safely.

---

## Deletion Requirements
### What “Remove game” means
When removing a game, the app should remove:
1. The installed game directory:
   - `<library_root>/steamapps/common/<installdir>`
2. The corresponding manifest:
   - `<library_root>/steamapps/appmanifest_<appid>.acf`

Additionally (optional but recommended, and should be configurable):
3. Proton/compatdata:
   - `<library_root>/steamapps/compatdata/<appid>/`  (if exists)
4. Shader cache:
   - `<library_root>/steamapps/shadercache/<appid>/` (if exists)
5. Download cache artifacts (optional, be conservative):
   - `<library_root>/steamapps/downloading/<appid>/`
   - `<library_root>/steamapps/temp/<appid>/` (if present)

### Safety / Confirmation
- Deleting is destructive. Require confirmation:
  - Show a modal dialog listing EXACT paths that will be deleted.
  - Require user to type the game name or appid to confirm OR press a “Hold to confirm” button for 2 seconds.
- If Steam is detected running:
  - warn and require additional confirmation.

### Permissions / Errors
- If deletion fails (permissions, file locked, etc.), show error details:
  - which path failed
  - exception message
- Support “dry-run mode” toggle to preview actions without deleting.

### Atomicity / Consistency
- Deletion should be best-effort and proceed in steps.
- If game directory deletion fails but manifest deletion succeeds, show a warning and propose “retry”.

---

## GUI Requirements
### Overall Layout
- Top toolbar row:
  - **Plus button**: Add mount point (directory chooser)
  - **Minus button**: Remove selected games (based on checkboxes)
  - Optional: “Rescan” button
  - Optional: “Theme” toggle (Light/Dark/Auto)

### Main List: Grid/Table
Columns:
1. Checkbox (select game)
2. Game Name
3. Location (mount point or library root path)
4. Trash button (icon) — remove this single game immediately (with confirmation)

Sorting / usability:
- Click column headers to sort by Name or Location.
- Search box optional but helpful (filter by name).

Status display:
- Bottom status bar: “N libraries, M games found”.
- Show scanning progress (spinner / progress bar).

### Theme (Dark/Light)
- Must allow switching between Dark and Light at runtime.
- If toolkit supports “System/Auto”, include it; otherwise provide at least Dark/Light.

---

## Data Model
Maintain an internal model like:

- MountPoint:
  - path
  - detected_libraries: [LibraryRoot]

- LibraryRoot:
  - root_path
  - steamapps_path
  - common_path

- GameEntry:
  - appid (string or int)
  - name (string)
  - installdir (string)
  - library_root (path)
  - install_path (path)
  - manifest_path (path)
  - optional_paths_to_delete (compatdata/shadercache/etc)
  - state: OK | MissingInstallDir | MissingManifest | Error

---

## Behavior
### Add Mount Point (+)
1. User selects a directory.
2. Scan that directory for Steam library roots:
   - Check directory itself and also `SteamLibrary` inside it.
   - Optionally search shallowly (depth 2) for directories that contain `steamapps`.
3. For each found library root:
   - Enumerate games via manifests.
4. Append newly found games at bottom (do not duplicate existing appid+library_root).

### Remove Selected (-)
1. Collect all checked GameEntry rows.
2. Show confirmation modal listing all targeted deletions.
3. On confirm, delete with progress reporting.
4. Remove deleted rows from the table.
5. If some deletions failed, keep those rows and show error state.

### Remove Single (Trash icon)
Same as Remove Selected but only for that row.

### Rescan (if implemented)
- Re-scan all added mount points and refresh the table.

---

## Technology Choice (Implementation Freedom)
Choose a GUI toolkit that makes a table with per-row buttons and theme toggling easy.
Recommended:
- Qt (PySide6 or PyQt6) preferred for table widgets + icons + styling
- Tkinter acceptable if table+buttons are manageable (e.g., ttk.Treeview + custom handling), but Qt is likely simpler.

Use standard Python libraries where possible.
Avoid requiring Steam APIs; this should be filesystem-based.

---

## Non-Goals
- No need to manage Steam login, downloads, or launching games.
- No need to parse every KeyValues nuance; just parse enough to get name/appid/installdir reliably.
- No need for perfect UI polish; correctness and safety first.

---

## Deliverables
1. A runnable Python application:
   - `main.py` (or package structure)
2. Clear README:
   - how to run
   - dependencies
   - notes about paths and permissions
3. Defensive logging:
   - log scan results and deletion operations (to console or a log file)

---

## Test Checklist
- Add a mount point containing SteamLibrary → games appear.
- Add two mount points → combined list appears.
- Trash delete single game → game directory and manifest removed.
- Minus delete multiple → all removed.
- Dry-run mode shows what would be deleted.
- Theme toggles dark/light without restart.
- Missing install dir shows warning but still removable (manifest cleanup).
