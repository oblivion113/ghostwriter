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

## RPC isolation

Each transformation starts:

```text
pi --mode rpc --no-tools --no-extensions --no-skills --no-prompt-templates
```

It also supplies a transformation-only system prompt and runs from its own cache directory, avoiding project context and tool access. Authentication and model configuration still come from Pi.

A unique session directory is created below the platform cache directory. The RPC process remains alive while the result is reviewed and revision feedback is exchanged. On acceptance, rejection, or failure, Ghostwriter closes the process and **deletes that cached session directory by default**. A hard process or machine crash may leave residue for later manual cleanup.

## Review loop

1. Press `F4` or select **Rewrite**.
2. Choose translation and/or tidying.
3. Set source and target languages.
4. Optionally set a Pi provider and model. Blank fields use Pi's default; when available, the selected Pi TUI target's current model pre-fills the fields.
5. Select **Run** or press `Ctrl+Enter` to start Pi RPC.
6. Review the returned draft.
7. Accept, reject, edit directly, or provide revision feedback.
8. Revisions reuse the same live RPC conversation.

The accepted result returns only to Ghostwriter. It is never injected into Pi's visible editor until the separate **Inject into Pi** action is used.
