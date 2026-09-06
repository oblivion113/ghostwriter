# Translation and rewrite workflow

Ghostwriter can use an isolated Pi RPC process to translate, tidy, or translate and tidy a draft before it is injected into Pi.

## Attachment integrity

Attachments inserted through Ghostwriter appear in the editor as compact display markers such as:

```text
@diagram.png
```

Before model processing, each occurrence is replaced with a random opaque token:

```text
__GW_94A72D61F5CE903B_ATTACHMENT_0000__
```

Only the opaque token and prose are sent to the model. The attachment path, filename, image bytes, and local token mapping are not sent. After the response, Ghostwriter verifies that every expected opaque token occurs exactly once before restoring the local markers. Missing, changed, unexpected, or duplicated placeholders prevent acceptance. One automatic repair request is attempted in the same session before reporting an integrity failure.

Final Pi serialization happens later. The bridge client replaces local markers with Pi's file or image syntax.

## RPC isolation and lifetime

When warm mode is enabled, app startup launches one background process:

```text
pi --mode rpc --no-tools --no-extensions --no-skills --no-prompt-templates
```

It receives a transformation-only system prompt and runs from a private cache directory, avoiding project context and tool access. Authentication and model configuration still come from Pi. By default, the process starts on demand and closes after each rewrite workflow to minimize idle memory. Keeping it warm is an opt-in that removes repeated CLI and model-runtime startup cost.

Before the first rewrite, Ghostwriter selects the configured model. Before every later rewrite workflow, it sends Pi's `new_session` command and then `set_model`; this prevents one draft's conversation from leaking into another while retaining the warm process. Review revisions continue in the current conversation. The RPC reader discards streaming update events after parsing and retains only completion signals, preventing queued partial-response snapshots from increasing memory use. The process is terminated and the entire private session directory is deleted when Ghostwriter exits. A hard process or machine crash may leave residue for later manual cleanup.

Set `rewrite.keepRpcWarm` to `true` to prewarm the process and retain it across workflows.

## Unified configuration

On first start, Ghostwriter writes `config.json` under `user_config_path("ghostwriter")`. The `rewrite` object defines:

- `keepRpcWarm`: whether app startup prewarms and retains the RPC process; defaults to `false`;
- `agents`: ordered `{provider, model}` choices; the first entry is the default, and a pair of blank values offers Pi's default;
- `targetLanguages` and `defaultTargetLanguage`: the language dropdown values and default;
- `instructions`: optional standing user directions, stored directly in JSON rather than an external file;
- `prompt`: a custom template supporting `{instructions}`, `{source_language}`, `{target_language}`, and required `{text}` placeholders.

The Rewrite dialog provides two configuration controls:

1. **Open config** launches the JSON file through the operating system's default associated editor.
2. **Refresh** validates the saved file, repopulates both dropdowns, and refreshes targets, Skills, and file search without restarting Ghostwriter.

The file is also reloaded immediately before each Rewrite dialog opens. A failed manual reload leaves the edited file untouched and keeps the last valid in-memory settings, so the user can correct it. A malformed file found during app startup is instead moved aside as `config.broken-<pid>.json` and replaced with safe defaults.

### Customization details

- Provider/model pairs must be unique and either both blank (Pi's default) or both contain IDs available from `pi --list-models`. Dropdown labels are derived as `provider/model`; no name field is used.
- The first agent is the default. `defaultTargetLanguage` must reference a value in `targetLanguages`.
- JSON comments are invalid and must not be added to `config.json`.
- `{text}` is the protected draft and is mandatory in every custom prompt.
- `{instructions}` contains the generated Translate/Tidy task list followed by the optional `instructions` field. Leave the field as `""` for no extra directions.
- `{source_language}` and `{target_language}` expose the selected language values.
- Custom prompts should retain a direct instruction to preserve every `__GW_*_ATTACHMENT_####__` token exactly once. Local integrity validation remains authoritative.

The generated default prompt treats attachment placeholders as immutable, tells the model to return only the draft, and explicitly forbids headings for short or single-section text.

## Review loop

1. Press `F4` or select **Rewrite**.
2. Choose translation and/or tidying.
3. Set source and target languages.
4. Choose a rewrite agent from the configured dropdown.
5. If needed, select **Open config**, save edits, and select **Refresh**.
6. Select **Run** or press `Ctrl+Enter`; the RPC starts on demand unless warm mode is enabled.
7. Review the returned draft.
8. Accept, reject, edit directly, or provide revision feedback. Revisions reuse the same live RPC conversation.

The accepted result returns only to Ghostwriter. It is never injected into Pi's visible editor until the separate **Inject into Pi** action is used.
