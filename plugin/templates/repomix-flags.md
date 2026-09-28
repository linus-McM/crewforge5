# Repomix pack flags

From the retired `use-repo-code` skill (spec phase 8). The recon ladder (`rules/recon-ladder.md`) and team-sprint's recon instruments point here. `crewforge5 knowledge pack <stage>` builds the commit-pinned per-stage packs with its own frozen exclude list; these flags are for a whole-repo text-grep pack.


Base command (all sizes):

```bash
repomix --compress --style xml --remove-comments --remove-empty-lines \
  --truncate-base64 --top-files-len 20 -o "$PACK" --ignore "<ignore-list>"
```

## Ignore list

Always exclude derived artifacts and lockfiles — they pollute greps with noise that
looks like findings (e.g. committed knowledge-graph JSON matching security patterns):

```
**/node_modules/**,**/dist/**,**/build/**,**/.next/**,**/.expo/**,**/coverage/**,
**/cdk.out/**,**/*.lock,**/package-lock.json,**/bun.lockb,**/yarn.lock,
**/graphify-out/**,**/.repomix-output.xml,**/.venv/**,**/__pycache__/**,**/target/**
```

## By repo size

| Repo size | Flags | Notes |
|---|---|---|
| Small (<5k LOC) | base flags; consider dropping `--compress` | Full bodies fit; compression loses more than it saves. PowerShell in particular compresses poorly (Tree-sitter grammar keeps little beyond `function` lines) — prefer uncompressed for PS-heavy repos. |
| Medium (5k–50k LOC) | base flags | The default sweet spot. |
| Large (50k–200k LOC) | base + `--include "src/**,lib/**"` per module | Pack per top-level module; one giant pack makes `-A` windows useless. |
| Very large (>200k LOC) | pack only the module under audit | Whole-repo packs exceed practical grep signal. |

## Freshness

Regenerate when missing or older than 2 hours (`[ $(( $(date +%s) - $(stat -c %Y "$PACK") )) -le 7200 ]`). Multi-agent flows:
regenerate once at flow start so every agent greps the same snapshot.

## Searching the pack

Search with `rtk grep '<pattern>' "${REPOMIX_PACK:-.repomix-output.xml}"`, never bare grep (full-width XML lines flood the context). A hit does not carry its filename: attribute it by reading the live file. The pack is `--compress`ed, so signatures survive and bodies may not.


## Finding the file block itself (any language)

```
^<file path="path/to/expected\.ext">$        # exact file exists?
<file path="[^"]*services/                   # everything under a directory
```

## TypeScript / JavaScript

| Question | Pattern |
|---|---|
| Symbol defined? | `function CreateThing\|const CreateThing\|class CreateThing` |
| Exported? | `export (default )?(function\|const\|class) CreateThing` |
| Route handler exists? | `(get\|post\|put\|delete)\(['"]/v1/foo` |
| Test coverage? | `describe\(['"]CreateThing\|it\(['"].*creates` |
| Layer violation? | `import .* from '@/services` (inside UI/store files) |
| Type escape hatches | `: any\|as any\|@ts-ignore\|@ts-expect-error` |

## Go

| Question | Pattern |
|---|---|
| Symbol defined? | `func (\(\w+ \*?\w+\) )?CreateThing` |
| Interface? | `type Thing interface` |
| Test coverage? | `func TestCreateThing` |
| Error swallowed? | `_ = err\|err != nil \{\s*$` |

## Python

| Question | Pattern |
|---|---|
| Symbol defined? | `def create_thing\|class CreateThing` |
| Test coverage? | `def test_create_thing` |
| Type escape hatches | `# type: ignore\|Any\]` |
| Error swallowed? | `except.*:\s*pass\|except Exception:` |

## Rust

| Question | Pattern |
|---|---|
| Symbol defined? | `fn create_thing\|struct CreateThing\|impl CreateThing` |
| Test coverage? | `#\[test\]` near `create_thing` |
| Panic paths | `\.unwrap\(\)\|\.expect\(\|panic!` |

## PowerShell

Verb-Noun naming means symbol greps anchor on the verb list. `.psd1` manifests and
`.psm1` loaders are the contract surface — grep them first.

| Question | Pattern |
|---|---|
| Cmdlet/function defined? | `function\s+(Get\|Set\|New\|Remove\|Invoke\|Import\|Export\|Test\|Backup\|Restore)-\w+` |
| Specific cmdlet? | `function\s+Invoke-RsMigration\b` |
| Exported from module? | `FunctionsToExport\|Export-ModuleMember` |
| Advanced function? | `\[CmdletBinding\|\[Parameter\(` |
| Return contract declared? | `\[OutputType\(` |
| Input validation? | `\[ValidateSet\|\[ValidateNotNull\|\[ValidateScript` |
| Test coverage (Pester)? | `Describe\s+['"].*Invoke-RsMigration\|It\s+['"]` |
| Error handling style | `catch\s*\{\|-ErrorAction\|\$ErrorActionPreference\|throw\s` |
| Destructive-op guard | `SupportsShouldProcess\|ShouldProcess\(\|-WhatIf\|-Confirm` |
| Output/logging drift | `Write-(Host\|Verbose\|Warning\|Error\|Information\|Debug)` |
| Secrets handling | `ConvertTo-SecureString\|AsPlainText\|ConvertFrom-SecureString\|Get-Credential` |
| SQL surface | `Invoke-Sqlcmd\|Invoke-DbaQuery\|SqlClient\|-Query\s` |
| Module dependencies | `RequiredModules\|Import-Module\|using module` |

## Generic (any stack)

| Question | Pattern |
|---|---|
| TODO debt | `TODO\|FIXME\|HACK\|XXX` |
| Hardcoded secrets | `(api[_-]?key\|secret\|password\|token)\s*[:=]\s*['"][^'"$]` |
| Env var usage | `process\.env\.\|os\.environ\|env::var\|\$env:` |
