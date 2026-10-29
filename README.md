# asd-ste100-ru — Simplified Technical Russian for AI agents

An agent skill that makes AI agents write **Russian** text that cannot be misread: short sentences, one meaning per word, active voice, no bureaucratese, and no slang calques. It adapts the rules of [ASD-STE100 Simplified Technical English](https://www.asd-ste100.org/) to Russian grammar.

The skill follows the open [Agent Skills](https://agentskills.io/) format (`SKILL.md` + folders). It works in Claude Code, Codex CLI, OpenCode, Hermes Agent, and any other agent that loads `SKILL.md` skills.

> Русская версия описания: [README.ru.md](README.ru.md).

## What it is

ASD-STE100 is a controlled-language standard from the European aerospace and defence industry. It exists because a misread maintenance instruction on an aircraft can kill people. The standard removes the two main sources of misreading: words with several meanings and sentences with several possible structures.

ASD-STE100 defines English only. This skill carries the same discipline into Russian. Some rules transfer directly: sentence length, active voice, one instruction per sentence, no semicolons, keep hedges. Other rules needed Russian-specific replacements:

| English STE rule | Russian adaptation |
|---|---|
| No phrasal verbs ("spin up", "reach out") | No slang calques: «пофиксить», «заапрувить», «засетапить», «задеплоить» |
| Verb, not noun ("perform an analysis") | No verbal-noun constructions and *kantselyarit* (bureaucratese): «осуществить проверку», «провести анализ», «в случае если», «посредством», «является» |
| No present perfect | Clear verb aspect, no needless compound forms («будет являться», «было бы произведено») |
| Noun clusters ≤ 3 words | Genitive chains ≤ 3 nouns: «проверка корректности заполнения полей формы» |
| 20 / 25 words per sentence | 18 / 22 words: Russian has no articles, so the same content needs fewer words |
| — | Direct word order where nominative and accusative look the same: «Сервер обновляет клиент» — who updates whom? |
| — | One participle clause per sentence; no dangling gerunds: «Проверив конфиг, файл удаляется» |
| — | Unambiguous pronouns, no double negation, code identifiers kept verbatim in backticks |

This is an adaptation, not an official standard. For English text, use the original [danyuchn/asd-ste100-skill](https://github.com/danyuchn/asd-ste100-skill).

## Why you need it

Agents write Russian the way bad technical documents do: long sentences, «осуществляется», «в рамках», «данный», passive voice with no actor, and English slang conjugated as Russian verbs. A person can guess what the author meant. Another agent, a translation pipeline, or a tired engineer at 3 a.m. guesses wrong.

The skill helps in these places:

- **Agent answers and reports.** Short, direct answers that say who did what and how sure the agent is.
- **Prompts, system messages, and tool descriptions.** Instructions another model reads without a human to ask.
- **Error messages and logs.** One fact per sentence and honest uncertainty: «Запрос мог не выполниться» stays a hedge and never becomes «Запрос не выполнился».
- **Documentation, READMEs, PR descriptions.** A softer mode keeps the structure rules but leaves room for natural prose.

## Benefits

- **Fewer misreadings between agents.** Inter-agent instructions have one possible parse.
- **Honest confidence.** The skill never turns a hedge into a fact and never adds a cause, frequency, or mechanism that the source did not state.
- **Consistent terminology.** One name for one thing in the whole document. A project glossary (for example `CONTEXT.md`) becomes the approved vocabulary.
- **Shorter text without lost facts.** Conditions, safety warnings, numbers, and scope limits stay. When shortening would lose precision, the skill keeps the long form and says so.
- **Deterministic check.** A stdlib-only Python linter finds the mechanical problems before a human reviews the text.

## Example

**Before** (tool description):

> Данный инструмент будет пытаться осуществить синхронизацию состояния между различными настроенными бэкендами, и в случае обнаружения конфликта он может разрешить его автоматически в зависимости от выбранной стратегии, а в противном случае конфликт будет вынесен на ручное рассмотрение.

**After:**

> Инструмент пытается синхронизировать состояние между настроенными бэкендами. Если инструмент находит конфликт, он читает выбранную стратегию. Если стратегия разрешает автоматическое решение, инструмент может решить конфликт сам. Если инструмент не решил конфликт, он передаёт конфликт на ручное рассмотрение.

The 36-word sentence became four sentences with one action each. The rewrite removed «данный», «осуществить синхронизацию», «в случае обнаружения», and the passive «будет вынесен». The hedges «пытается» and «может» stayed: the tool does not promise success. More examples: [examples/before-after.md](examples/before-after.md).

## Installation

### Option 1 — ask your AI agent to install it

Copy the prompt below and paste it into your agent (Claude Code, Codex, OpenCode, Hermes Agent, Cursor, or another agent with shell access). The agent installs the skill once and connects it to every supported agent it finds on your machine.

````text
Install the agent skill "asd-ste100-ru" from https://github.com/wh1tespirit/asd-ste100-ru for all AI agents on this machine. Follow these steps exactly.

1. Clone the repository into the shared skills folder:
   git clone https://github.com/wh1tespirit/asd-ste100-ru.git ~/.agents/skills/asd-ste100-ru
   Create ~/.agents/skills first if it does not exist. If ~/.agents/skills/asd-ste100-ru already is a clone of this repository, run "git -C ~/.agents/skills/asd-ste100-ru pull --ff-only" instead. If it exists but is something else, stop and ask me.
   On Windows, use %USERPROFILE%\.agents\skills\asd-ste100-ru.

2. Check that ~/.agents/skills/asd-ste100-ru/SKILL.md exists and that its YAML frontmatter contains "name: asd-ste100-ru".

3. Connect the skill to each agent that is installed here. An agent is installed if its config folder exists. For each such agent, create a symbolic link named asd-ste100-ru inside its user skills folder that points to ~/.agents/skills/asd-ste100-ru. On Windows, create a directory junction with: mklink /J <link> <target>. Create the skills folder if it is missing.
   - Claude Code (~/.claude exists): link in ~/.claude/skills/
   - Codex CLI: reads ~/.agents/skills/ directly. Do not create a link.
   - OpenCode (~/.config/opencode exists): reads ~/.agents/skills/ directly. Create a link in ~/.config/opencode/skills/ only if the environment variable OPENCODE_DISABLE_EXTERNAL_SKILLS is set.
   - Hermes Agent (~/.hermes exists): link in ~/.hermes/skills/writing/
   - Any other agent that supports SKILL.md skills: link in its user-level skills folder, if you know that folder for certain. If you are not sure, list the agent in the report and do not guess.
   If a file or folder named asd-ste100-ru already exists in a target folder and is not a link to ~/.agents/skills/asd-ste100-ru, do not change it. Report it to me.

4. If python3 is available, run:
   python3 ~/.agents/skills/asd-ste100-ru/scripts/ste-lint.py --selftest
   The expected output is "selftest OK". If python3 is not available, skip this step and say so. The skill works without Python. Only the optional linter needs it.

5. Do not change any other files, settings, or agent configuration.

6. Report in a short list: the install path, each link you created, each agent you skipped and why, and the selftest result. Then tell me to restart my agents so that they load the new skill.
````

### Option 2 — skills CLI

The [skills CLI](https://skills.sh/) installs the skill for the agents it supports:

```bash
npx skills add wh1tespirit/asd-ste100-ru -g
```

The CLI sends anonymous install telemetry. Set `DISABLE_TELEMETRY=1` to turn it off.

### Option 3 — manual install

Clone once into the shared folder, then link it where each agent looks for skills.

```bash
git clone https://github.com/wh1tespirit/asd-ste100-ru.git ~/.agents/skills/asd-ste100-ru

# Claude Code
mkdir -p ~/.claude/skills && ln -s ~/.agents/skills/asd-ste100-ru ~/.claude/skills/asd-ste100-ru

# Hermes Agent
mkdir -p ~/.hermes/skills/writing && ln -s ~/.agents/skills/asd-ste100-ru ~/.hermes/skills/writing/asd-ste100-ru
```

| Agent | User skills folder | Note |
|---|---|---|
| Codex CLI | `~/.agents/skills/` | Reads the shared folder directly. Older versions read `~/.codex/skills/` — link there if your version does not see the skill. |
| OpenCode | `~/.config/opencode/skills/` | Also reads `~/.agents/skills/` and `~/.claude/skills/`, unless `OPENCODE_DISABLE_EXTERNAL_SKILLS` is set. |
| Claude Code | `~/.claude/skills/` | Link required. |
| Hermes Agent | `~/.hermes/skills/<category>/` | Link required. Skills are grouped in category folders. |
| Other agents | Agent-specific | Any agent that supports the Agent Skills format. Put or link the folder where that agent reads `SKILL.md` skills. |

Project-level install: clone into `.agents/skills/asd-ste100-ru` (or `.claude/skills/`, `.opencode/skills/`) inside the repository.

Update: `git -C ~/.agents/skills/asd-ste100-ru pull --ff-only`. Restart the agent after install or update.

## Usage

The agent loads the skill when the task matches its description. You can also ask for it directly:

```text
Перепиши это сообщение об ошибке по asd-ste100-ru.
Убери канцелярит из этого README.
Rewrite this tool description with asd-ste100-ru so another agent cannot misread it.
Покажи до/после и какие правила нарушены.
```

To make an agent **always** answer in this style, add one line to your project instructions (`AGENTS.md`, `CLAUDE.md`, or the equivalent):

```markdown
Для ответов на русском всегда используй навык asd-ste100-ru.
```

### Two modes

- **Strict** — procedures, error messages, tool descriptions, prompts, inter-agent instructions. All rules apply.
- **Soft** — READMEs, PR descriptions, explanations, answers to users. Structure rules apply in full. Word-choice rules are advice, so the prose stays natural.

By default the skill returns only the rewritten text. Ask for "до/после" or "какие правила нарушены" to get a table of violations.

## Linter

`scripts/ste-lint.py` checks the mechanical rules with the Python standard library only.

```bash
python3 scripts/ste-lint.py --selftest
python3 scripts/ste-lint.py docs/*.md
echo "Выполните проверку конфигурации." | python3 scripts/ste-lint.py --json
python3 scripts/ste-lint.py --baseline 10 --disable passive-voice README.md
```

- Hard rules (exit code 1): `semicolon`, `long-sentence`, `jargon-verb`, `marketing-adjective`, `bureaucratese`, `nominalization`, `synonym-rotation`, `dangling-conjunction`.
- Advisory rules (never fail the run): `passive-voice`, `verbose-copula`, `double-negation`.
- The linter **never** flags hedges such as «может», «мог», «возможно», «вероятно». Confidence is content.

The linter uses regular expressions, not a morphological parser. It does not check word order, genitive chains, participle clauses, or pronoun reference. Those rules are in `SKILL.md` for the agent to apply. A clean result means only that the configured checks found nothing. It does not prove that a rewrite kept the meaning.

## Files

| Path | Content |
|---|---|
| `SKILL.md` | The skill: rules, modes, process, output format |
| `references/writing-rules.md` | STE rule sections, the Russian adaptation of each, sources |
| `examples/before-after.md` | Before/after examples |
| `examples/linter-edge-cases.md` | Fixture with two intentional linter findings |
| `scripts/ste-lint.py` | Deterministic linter |

## Limitations

- ASD-STE100 defines English only. These Russian rules are an adaptation, not a certified standard.
- The 18 / 22 word limits are an estimate from the English limits, not a value from the standard.
- STE fixes the form of a text, not its content. An empty paragraph stays empty after the rewrite.
- Not for fiction, marketing, or persuasive text, where voice is the point.

## Credits

- Based on [danyuchn/asd-ste100-skill](https://github.com/danyuchn/asd-ste100-skill) (MIT) by Dustin Yuchen Teng.
- ASD-STE100 is maintained by [ASD](https://www.asd-ste100.org/). This project does not reproduce the standard's dictionary.
- Russian-specific guidance draws on GOST 2.105 (general requirements for text documents), K. Chukovsky's term *kantselyarit*, and Nora Gal's «Слово живое и мёртвое».

## License

MIT — see [LICENSE](LICENSE).
