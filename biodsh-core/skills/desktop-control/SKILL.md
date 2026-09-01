---
name: desktop-control
description: See and drive the user's desktop without vision - list and focus windows, read on-screen controls and text as JSON with coordinates (UI Automation on Windows, OCR elsewhere), then click, type, send hotkeys, open apps and paste tables into Excel/SPSS/GraphPad Prism/Zotero.
---

# Desktop control (for text-only agents)

Use this skill when the user asks you to operate a program on their computer: "把这个表贴进 Excel 存成 xlsx", "打开 Zotero 把这篇 DOI 加进去", "在 Prism 里新建一个数据表", "帮我点一下那个按钮". You cannot see pixels, so you **read the screen as text with coordinates** and act on those coordinates. Every command prints one JSON object; on failure the exit code is 1 and the JSON has `"ok": false, "error", "hint"`.

Run it with the BioDSH Python: `python "<skill dir>/control.py" <subcommand> ...` (Windows: `bioenv\.venv\Scripts\python.exe`). Screenshots go to `./desktop_control/` under the working directory unless `--out` is given.

Requires pyautogui, mss, pyperclip, pillow, pywinauto (Windows), plus rapidocr-onnxruntime for OCR and pandas for `paste-table`. The BioDSH app installs all of them through the env pack **"电脑控制"**; if a command reports a missing package, tell the user to install that pack (or run the `uv pip install ...` line from the hint) - do not try other tools.

## The loop (always)

1. `windows` - list open windows (`title`, `process`, `pid`, `rect`, `minimized`, `foreground`). Confirm the target app is there; if not, `open <app>` then `wait 3` and list again.
2. `focus --window "<title substring>"` - bring it to the front. Check the returned `focused.title` really is the app you meant (`other_matches` lists the other candidates; use a more specific substring if needed).
3. `inspect --window "<substring>"` - **primary way to see** (Windows): every control's `name`, `control_type`, center `x`,`y`, `enabled`, `auto_id`, and `value` for edit boxes. Use `--name "<text>"` to filter, `--max` to widen. On macOS/Linux it returns `unsupported: true` - use `screenshot --ocr --window "<substring>"` instead, which gives text lines with center coordinates.
4. Act: `click x y`, `click-text "<label>"`, `type "<text>"`, `hotkey ctrl s`, `press enter`, `paste-table data.csv`.
5. `inspect` (or `screenshot --ocr`) **again** to verify the effect (new window title, dialog gone, edit box `value` now holds the text). Never assume an action worked.
6. Finish with `screenshot --out <job dir>/desktop_control/final.png` and report its path to the user as evidence, together with what you did.

```
python "<skill dir>/control.py" windows
python "<skill dir>/control.py" focus --window "Zotero"
python "<skill dir>/control.py" inspect --window "Zotero" --name "Add"
python "<skill dir>/control.py" click-text "Add Item(s) by Identifier" --window "Zotero"
python "<skill dir>/control.py" type "10.1038/s41586-020-2649-2" --enter
python "<skill dir>/control.py" screenshot --ocr --window "Zotero"
```

## Commands

| Command | What it does |
|---|---|
| `windows [--filter s]` | List visible top-level windows. |
| `focus --window s` | Raise/restore the window whose title contains `s`. |
| `inspect --window s [--depth 12] [--max 300] [--name s] [--all]` | UI Automation control tree (Windows). |
| `screenshot [--out p] [--ocr] [--region x y w h] [--window s]` | Save PNG; `--ocr` adds `ocr: [{text,x,y,rect,score}]` sorted top-to-bottom. |
| `find-text "s" [--window s] [--ocr]` | Locate text: UIA control names first, OCR fallback; `best: {x,y}`. |
| `click x y [--button right] [--double]`, `click-text "s"`, `move x y`, `scroll -5 [--x --y]` | Mouse. |
| `type "text" [--enter]`, `hotkey ctrl shift s`, `press tab [--times 3]` | Keyboard. Non-ASCII text (Chinese) is pasted via the clipboard automatically. |
| `open excel` / `open zotero` / `open prism` / `open C:\path\file.xlsx` / `open https://...` | Launch by alias, path or URL. |
| `wait 2` | Sleep. |
| `clipboard [--set "text"]` | Read or set the clipboard. |
| `paste-table data.csv [--sep auto] [--no-header] [--no-paste]` | Load a CSV/TSV as tab-separated text onto the clipboard and press Ctrl+V - the fastest way to move data into Excel / SPSS / Prism grids. |
| `info` | Screen size, mouse position, which packages are installed. |

## Speed: batch your actions

Every tool call costs a model round-trip, so do NOT issue one command per click. Plan a short sequence, run it in ONE call with `batch`, and read the returned results:

```bash
python "<skill dir>/control.py" batch '[["focus","--window","Excel"],["hotkey","ctrl","home"],["paste-table","table.csv"],["wait","1"],["screenshot","--ocr","--window","Excel"]]'
```

Shell quoting mangles inline JSON (PowerShell especially) — write the steps to a file in the workspace and pass `@steps.json`:

```bash
python "<skill dir>/control.py" batch @steps.json
```

`batch` stops at the first failed step (add `--continue-on-error` to keep going) and returns each step's JSON. Typical rhythm: one `batch` to act + verify, look at the result, one more `batch` to finish. Call `overlay` once at the start of a task so the user sees that BioDSH is taking control.

## Rules

- `--window` also accepts `process:<exe name>` (e.g. `--window process:EXCEL.EXE`) — use it when several windows share a title (a project name shown by two apps).

- Multi-monitor: `focus` / `--window` automatically move a window that opened on a second monitor onto the primary screen, because screenshots and coordinates are reasoned about on the primary screen. If a dialog still appears elsewhere, `windows` lists every window with its rect — negative or large coordinates mean another monitor.

- **Always pass `--window <title>` to `click` / `click-text` / `type` / `hotkey` / `press` / `paste-table` / `scroll`.** The target app is often NOT in front (the user's chat window, a dialog, another app); with `--window` the command brings it to the front and refuses to act if it cannot, instead of clicking into the wrong program. Without it the result reports which window actually received the action.

- Every mouse/keyboard command glides the cursor smoothly to its target and shows the BioDSH control overlay (a glass pill 「BioDSH 正在控制电脑」 at the top of the screen + a soft glow around the cursor; state lives in `<workspace>/.biodsh_control/`, which you may ignore). It disappears by itself ~25 s after the last action. Tell the user this is expected and that slamming the mouse into a screen corner aborts immediately.

- `open` on Windows hands the launch to the Explorer shell, so the app starts **outside the BioDSH sandbox** with the user's normal permissions and keeps running after the command returns. Never start GUI apps with `Start-Process` / `subprocess` from a tool call instead: they inherit the write-restricted sandbox token (Excel then complains 「内存或磁盘空间不足」 on save) and are killed when the call ends. After `open`, wait 3–10 s, then `windows` / `focus`.
- Big apps (Excel, Word, Prism) have huge control trees: use `inspect --name <text>` or `--depth 4`, and fall back to `screenshot --ocr --window <title>` if `inspect` is slow.

- **Verify the window title before every action.** If `focus` returns a different app than intended, stop and pick a better substring; never click blind.
- **Prefer `inspect` control names over OCR**; OCR is for canvases, images and non-Windows. Use the `x`,`y` from the JSON exactly; do not guess coordinates.
- **Ask the user before anything destructive**: closing an app with unsaved work, overwriting a file, sending a message/email, confirming a dialog you did not expect. Report what the dialog says and wait.
- **Two tries, then stop.** If a control or text cannot be found after two attempts (with an `inspect`/`screenshot --ocr` in between), stop and report what *is* on screen instead of trying random clicks.
- Only do what the user asked; do not explore menus, open other apps or change settings on your own.
- Keep the mouse away from screen corners (moving it into a corner aborts the tool - the user's emergency stop). If a command returns `FailSafeException`, stop and ask the user.
- Windows coordinates are physical pixels (DPI-aware); pass them straight back to `click`.

## Worked example: put a CSV into Excel and save as xlsx

```
open excel            -> wait 4 -> windows            # confirm a title containing "Excel"
focus --window "Excel"
inspect --window "Excel" --name "Blank workbook"       # start screen? then:
click-text "Blank workbook" --window "Excel"  ; wait 2
inspect --window "Excel" --name "A1"                   # cell A1 exists, sheet is ready
click <x> <y of A1>                                    # or press ctrl home
paste-table results.csv                                # tab-separated -> pastes into the grid
inspect --window "Excel" --name "B2"                   # verify: value of a cell matches the CSV
hotkey f12                                             # Save As dialog
inspect --window "Save As" --name "File name"          # find the Edit control, click it
type "C:\Users\me\Desktop\results.xlsx" --enter
wait 2 ; windows                                       # title now "results.xlsx - Excel"
screenshot --out desktop_control/excel-final.png       # report this path
```
If a "file already exists" dialog appears, do not confirm it - ask the user.

## Worked example: add a paper to Zotero by DOI via the Zotero window

```
windows --filter Zotero          # if absent: open zotero ; wait 5
focus --window "Zotero"
inspect --window "Zotero" --name "Identifier"     # toolbar button "Add Item(s) by Identifier" (magic wand)
click-text "Add Item(s) by Identifier" --window "Zotero"
wait 1
type "10.1038/s41586-020-2649-2" --enter          # the popup Edit is focused after the click
wait 4
inspect --window "Zotero" --name "s41586"         # or search the article title; verify the new item row exists
screenshot --out desktop_control/zotero-final.png
```
Prefer the `zotero-connect` skill (local API) when it is available - it needs no clicking; use this GUI route only when that skill fails or the user asks for the GUI.
