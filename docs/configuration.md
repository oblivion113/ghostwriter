# Configuration

Ghostwriter creates `config.json` on first start using the platform's normal user configuration directory. On macOS, the default location is:

```text
~/Library/Application Support/ghostwriter/config.json
```

The simplest way to find and edit it is **Settings → Open config**. Save the file, return to Ghostwriter, and choose **Reload config**. Opening the Rewrite dialog also reloads the file automatically.

## Structure

The configuration has two sections:

- `fileSearch` controls `@` attachment discovery and ranking.
- `rewrite` controls Translate / Tidy models, languages, instructions, and process lifetime.

This focused example is valid; omitted fields use their defaults:

```json
{
  "version": 1,
  "fileSearch": {
    "includeHidden": false,
    "useGlobalFzfOptions": true,
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

## File search

| Field | Meaning |
| --- | --- |
| `includeHidden` | Include hidden files during `@` search. Defaults to `false`. |
| `useGlobalFzfOptions` | Inherit `FZF_DEFAULT_OPTS` and `FZF_DEFAULT_OPTS_FILE`. Set it to `false` for app-only behavior. |
| `skipDirectories` | Directory names omitted by both `fd` and the Python fallback, such as `.git`, `node_modules`, caches, and build outputs. Entries must be unique names, not paths. |
| `ignoreFiles` | Additional gitignore-format files passed to `fd`. Paths may use `~`. |
| `fzfOptions` | Extra command-line arguments used for non-interactive `fzf --filter` ranking. |

`fd` and `fzf` are optional. If either operation is unavailable or fails, Ghostwriter uses its bounded Python search and ranking fallback.

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

A failed manual reload leaves the edited file untouched and keeps the last valid in-memory configuration. Ghostwriter reports the error so you can correct the same file.

If the configuration is malformed during application startup, Ghostwriter moves it to `config.broken-<pid>.json` and creates a safe default replacement. JSON comments are not supported, so avoid `//` and `#` annotations.
