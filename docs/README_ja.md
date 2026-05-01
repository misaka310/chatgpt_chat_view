# ChatGPT Export Dashboard (Japanese)

## Purpose
This project analyzes ChatGPT export files and creates local dashboard artifacts.

## Safety Policy
- Raw chat content must not be committed to Git.
- Derived files generated from raw chat exports are also ignored by default.
- Only source code and documents under `docs/` should be versioned.

## Main Source File
- `analyze_chat_export.py`

## Typical Local Workflow
1. Place export files in the project root (`chat.html` or `conversations-*.json`).
2. Run the analysis script locally.
3. Open `dashboard.html` locally when needed.

## Rebuild Example
```powershell
python .\analyze_chat_export.py --input-dir . --output-dir . --timezone Asia/Tokyo --rebuild
```

## Incremental Example
```powershell
python .\analyze_chat_export.py --input-dir . --output-dir . --timezone Asia/Tokyo
```

## Version Control Notes
- `.gitignore` is configured to keep chat data and generated artifacts out of commits.
- If a tracked file accidentally includes chat content, remove it from index before commit.
