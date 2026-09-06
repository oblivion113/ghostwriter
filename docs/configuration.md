# Configuration

Ghostwriter creates `config.json` on first start using the platform's normal user configuration directory. On macOS, the default location is:

```text
~/Library/Application Support/ghostwriter/config.json
```

The simplest way to find and edit it is **Settings → Open config**. Save the file, return to Ghostwriter, and choose **Refresh**. This also refreshes Pi targets, Prompt templates, Skills, and file-search indexes, so files and templates created after launch become immediately searchable. Opening the Rewrite dialog reloads configuration only.

## Structure

The configuration has four sections:

- `ui` controls persistent interface preferences.
- `promptTemplates` selects the directory containing reusable Prompts.
- `fileSearch` controls `@` file and folder discovery and ranking.
- `rewrite` controls Translate / Tidy models, languages, instructions, and process lifetime.

This focused example is valid; omitted fields use their defaults:

```json
{
  "version": 1,
  "ui": {
    "theme": "nord"
  },
  "promptTemplates": {
    "directory": "~/Library/Application Support/ghostwriter/prompts"
  },
  "fileSearch": {
    "includeHidden": false,
    "useGlobalFzfOptions": true,
    "pathDisplay": "auto",
    "ignoreFiles": [],
    "fzfOptions": []
  },
  "rewrite": {
    "keepRpcWarm": false,
    "agents": [
      { "provider": "agent-plan", "model": "ark-code-latest" },
      { "provider": "anthropic", "model": "claude-haiku-4-5" }
    ],
    "targetLanguages": ["English", "Chinese (Simplified)", "French"],
    "defaultTargetLanguage": "English",
    "instructions": ""
  }
}
```

The generated file also contains the full default `skipDirectories` list and rewrite `prompt`.

## Interface

`ui.theme` sets the active theme and is updated automatically whenever a new theme is chosen from Ghostwriter's Theme palette. Available values are `textual-dark`, `nord`, `gruvbox`, `catppuccin-mocha`, `tokyo-night`, and `rose-pine-moon`.

## Prompt templates

`promptTemplates.directory` points to one folder containing `.md` Prompt templates. Ghostwriter's generated default is a `prompts` folder beside `config.json`, separate from Pi's `~/.pi/agent/prompts`. Paths may use `~`; the field may point to Pi's directory, although Ghostwriter intentionally supports only the simpler format below. Discovery is non-recursive.

```markdown
---
name: review
description: Review staged git changes
---
Review the staged changes carefully.

Focus on correctness and security.
```

`name` is required and accepts letters, numbers, periods, underscores, and hyphens. `description` is optional and may be blank; when present, it is a single-line value. The body is literal text and may contain Markdown and line breaks.

Choose **Prompts** to browse the folder. **Insert** adds the selected template as a `/prompt:<name>` reference, such as `/prompt:review`, at the cursor, while **Expand** expands all references already in the draft. `F3` performs the same expansion without opening the picker. **Open folder** opens the configured directory; use **Settings → Refresh** after templates are added or removed.

Inline completion follows the same grammar as Skills: type `/prompt:rev`, then press Tab or click the result to insert `/prompt:review`. If a referenced template was removed or renamed, expansion stops without partially changing the draft.

Pi argument expressions such as `$1`, `$@`, and `${@:2}` are not evaluated; they remain literal body text. Pi expands templates only inside its prompt-submission pipeline, and its extension API has no supported post-expansion interception point that can return the result without dispatching an Agent turn. Ghostwriter therefore avoids maintaining a second, potentially divergent implementation.

## File search

| Field | Meaning |
| --- | --- |
| `includeHidden` | Include hidden files and folders during `@` search. Defaults to `false`. |
| `useGlobalFzfOptions` | Inherit `FZF_DEFAULT_OPTS` and `FZF_DEFAULT_OPTS_FILE`. Set it to `false` for app-only behavior. |
| `pathDisplay` | `auto` shows paths relative to Pi's working directory for items inside it and absolute paths for items outside it. `full` always shows an absolute path. |
| `skipDirectories` | Directory names omitted by project and system-index search, such as `.git`, `node_modules`, caches, and build outputs. Entries must be unique names, not paths. |
| `ignoreFiles` | Additional gitignore-format files passed to `fd`. Paths may use `~`. |
| `fzfOptions` | Extra command-line arguments used for non-interactive `fzf --filter` ranking. |

Git's VCS ignore rules do not hide project `@` candidates, so local context listed in `.git/info/exclude` remains selectable. The explicit `skipDirectories` and `ignoreFiles` settings still remove unwanted project paths, and hidden paths remain controlled by `includeHidden`.

Project completion starts immediately after `@`. Once a filename query reaches three characters, Ghostwriter also searches outside the working directory through Spotlight on macOS or `locate` on other Unix systems. These indexed lookups are debounced, bounded, and run in a cancellable background worker; project candidates remain ahead of system candidates. `/` and `~` queries retain direct path completion.

`fd` and `fzf` are optional. If either operation is unavailable or fails, Ghostwriter uses its bounded Python project search and ranking fallback. Whole-computer results require an available operating-system file index.

## Rewrite settings

| Field | Meaning |
| --- | --- |
| `keepRpcWarm` | Keep one isolated Pi RPC process alive between rewrite workflows. Defaults to `false`, which starts it on demand and closes it afterward. |
| `agents` | Ordered `{provider, model}` choices shown in the Rewrite dialog. The first entry is the default. |
| `targetLanguages` | Unique language names shown in the target-language dropdown. |
| `defaultTargetLanguage` | Initial target language. It must appear in `targetLanguages`. |
| `instructions` | Optional standing directions appended to the generated Translate / Tidy requirements. |
| `prompt` | Template sent to the rewrite model after attachment markers have been protected. |

Provider and model IDs must match Pi's catalogue:

```bash
pi --list-models
```

Both values in an agent entry must be present. To offer Pi's current default model, leave both blank:

```json
{ "provider": "", "model": "" }
```

Agent pairs and target-language names must be unique.

## Custom rewrite prompts

`rewrite.prompt` supports four placeholders:

| Placeholder | Value |
| --- | --- |
| `{text}` | The protected draft. This placeholder is required. |
| `{instructions}` | Generated Translate / Tidy requirements followed by the standing `instructions` value. |
| `{source_language}` | The source language selected in the dialog. |
| `{target_language}` | The target language selected in the dialog. |

A custom prompt should tell the model to return the entire transformed draft and preserve every token matching this form exactly once:

```text
__GW_*_ATTACHMENT_####__
```

Ghostwriter validates placeholder integrity locally, but clear model instructions reduce repair attempts. See [`rewrite.md`](rewrite.md) for the complete protection and review flow.

## Reloading and recovery

A failed manual reload leaves the edited file untouched and keeps the last valid in-memory configuration. Ghostwriter reports the error so you can correct the same file. A successful **Refresh** also reloads Prompt templates and rebuilds runtime discovery state: Pi targets, Skills, the project file index, and cached whole-computer results.

If the configuration is malformed during application startup, Ghostwriter moves it to `config.broken-<pid>.json` and creates a safe default replacement. JSON comments are not supported, so avoid `//` and `#` annotations.
