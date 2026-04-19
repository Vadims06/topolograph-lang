# Language packs

Community-contributed translations for Topolograph public UI and SEO strings live under `lang/<locale>/`.

## Contributing a translation

1. Copy `lang/en/` to `lang/<locale>/` (use a BCP 47 language tag for the folder name, e.g. `ru`, `zh`).
2. Translate string values in `common.json` and `pages/*.json`. **Do not** rename keys.
3. Keep technical abbreviations unchanged — see `abbreviations.json` and the `protected` list (OSPF, IS-IS, Topolograph, etc.).
4. Open a pull request with a short note on what you translated and any context for reviewers.

## File layout

- `abbreviations.json` — terms that must not be translated in any locale.
- `<locale>/common.json` — shared navigation and UI chrome.
- `<locale>/pages/<page>.json` — per-page copy; SEO fields live under `_meta` (`title`, `description`, `meta_keywords`, `og_title`, `og_description`).

English (`en/`) is the reference catalog. Other locales should keep the same key structure.

## Cross-referencing UI labels in prose strings

Some prose strings quote the name of a UI element (button, tab, dropdown label) inline — for example, a description that says *"open the «Network reaction on failure» tab"*. When translating such a string, use the **translated form of that UI label**, not the English one.

- Find the key for the UI label (e.g. `btn_network_reaction` in `js_ui.json`).
- Copy its translated value into the prose string.
- Wrap it in guillemets (`«»`) for Russian or corner brackets (`「」`) for Chinese to keep it visually distinct.

Leaving the English label name in a translated prose string is the most common consistency mistake — it means the on-screen label and the description text no longer match.

## HTML in strings

**All string values must be plain text — no HTML tags.**
HTML structure (e.g. `<strong>`, `<b>`) belongs in the JS or template render code that uses the string, not inside the translated value.
If a key requires visual emphasis, add the markup in the calling code and keep the catalog value as plain prose.

## Protected terms and child forms (`abbreviations.json`)

For each `protected` entry, the translator also treats **child forms** as allowed English tokens:

- **Slash-separated compounds** (e.g. `RID/System ID`): the full string, each slash segment, and each word inside a segment (`RID`, `System`, `ID`, etc.) are all stripped when matching; you do not need separate entries for `RID` vs `System ID` if the compound is listed.
- **Plurals of ALL‑CAPS acronym slabs** (letters/digits only, e.g. `SPT`): `SPTs` is allowed automatically when `SPT` is listed; you normally do not need both `SPT` and `SPTs` unless you want an explicit extra form.