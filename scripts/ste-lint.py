#!/usr/bin/env python3
"""Детерминированный линтер структурных правил STE для русского текста.

Проверяет только правила, которые можно проверить без словаря и без
морфологического разбора. Линтер намеренно никогда не отмечает модальность
(может, мог, возможно, вероятно): навык считает степень уверенности
содержанием, а линтер, который давит на оговорки, меняет утверждения.

Использование:
    ste-lint.py FILE [FILE ...]
    echo "текст" | ste-lint.py [--json]
    ste-lint.py --baseline 5 FILE      # успех, пока жёстких нарушений не больше 5
    ste-lint.py --disable passive-voice,verbose-copula FILE
    ste-lint.py --selftest

Код 1 — жёстких нарушений больше базовой линии (по умолчанию 0).
Рекомендательные находки (passive-voice, verbose-copula, double-negation)
никогда не дают код 1. Код 2 — ошибка вызова (неизвестный флаг, плохое
значение, неизвестное правило, файл не читается).
"""
import argparse
import bisect
import contextlib
import io
import json
import os
import re
import sys
import tempfile

# Эвристики на регулярных выражениях, а не синтаксический разбор.
# Нет правил для цепочек родительного падежа, деепричастных оборотов и порядка
# слов: без морфологического анализатора они дают слишком много ложных находок.

# Прилагательное или причастие между глаголом и отглагольным существительным:
# «провести полную проверку».
_ADJ = r"\w+(?:ую|юю|ое|ее|ый|ий|ой|ые|ие|ей|ого|его)"
# Отглагольные существительные в формах, которые встречаются после
# «провести», «произвести» и подобных глаголов.
_DEVERBAL_ANY = r"\w+(?:ние|ния|нию|нием|нии|ция|ции|цию|цией|ка|ки|ку|кой|ке|из|иза|изу|изом)"
_DEVERBAL_NIE = r"\w+(?:ние|ния|нию|нием|нии)"
_PROD_VERB = (r"(?:произв|пров)(?:ести|едите|едём|едем|едёт|едет|едут|одить|одит|одят"
              r"|одите|одится|одятся|одим|ёл|ел|ела|ело|ели|едена|едено|едены|едён|еден)")
_VYPOLN_VERB = r"выполн(?:ить|ять|ите|яйте|ит|ят|яет|яют|ил|ила|ило|или|ено|ены|яется|яются)"
_GIVE_VERB = r"(?:да(?:ть|ёт|ет|ют|л|ла|ло|ли|йте|й)|дава(?:ть|ться|л|ла|ли|й|йте))"

RULES = [
    ("semicolon", "advisory-free",
     re.compile(r";"),
     "Точка с запятой запрещена (STE, правило 8.1). Раздели на отдельные предложения."),
    ("jargon-verb", "advisory-free",
     re.compile(
         r"\b(пофикс\w*|фиксану\w*|зарезолв\w*|резолвну\w*|заапрув\w*|апрувну\w*"
         r"|засетап\w*|сетапну\w*|пошар(?:ить|ил|ила|или|ь|ьте|ю|ит|ят)\b|зашар\w*|расшар\w*"
         r"|пингану\w*|чекну\w*|зачека\w*|заюза\w*|юза(?:ть|ет|ют|ем|л|ла|ли|й|йте)\b"
         r"|стартану\w*|апдейтну\w*|заапдейт\w*|заимплемент\w*|имплементну\w*"
         r"|засинк\w*|законтрибьют\w*|заскипа\w*|скипну\w*|задепло\w*)", re.I),
     "Жаргонный глагол-калька. Используй обычный глагол: исправить, одобрить, настроить, развернуть."),
    ("marketing-adjective", "advisory-free",
     re.compile(
         r"\b(бесшовн\w*|революционн\w*|инновационн\w*|молниеносн\w*|непревзойд[её]нн\w*"
         r"|беспрецедентн\w*|ультрасовременн\w*|высокотехнологичн\w*|невероятн\w*|потрясающ\w*"
         r"|передов(?:ой|ая|ое|ые|ого|ым|ых|ую|ыми|ому)\b"
         r"|мощн(?:ый|ая|ое|ые|ого|ой|ым|ых|ую|ыми|ому)\b"
         r"|не\s+имеющ\w*\s+аналогов|мирового\s+уровня)", re.I),
     "Рекламное прилагательное. Удали его или замени измерением, которое подтверждает оценку."),
    ("bureaucratese", "advisory-free",
     re.compile(
         r"\b(в\s+целях|в\s+рамках|на\s+предмет|имеет\s+место|имели\s+место|посредством"
         r"|в\s+связи\s+с\s+тем,?\s+что|ввиду\s+того,?\s+что|по\s+причине\s+того,?\s+что"
         r"|в\s+случае,?\s+если|в\s+случае\s+наличия|осуществл\w*"
         r"|осуществ(?:ить|ит|ят|ил|ила|ило|или|ите)\b)", re.I),
     "Канцелярит. Используй простое слово: «если», «потому что», «через», «для», точный глагол."),
    ("nominalization", "advisory-free",
     re.compile(
         r"\b(?:" + _PROD_VERB + r")\s+(?:" + _ADJ + r"\s+)?" + _DEVERBAL_ANY + r"\b"
         r"|\b" + _VYPOLN_VERB + r"\s+(?:" + _ADJ + r"\s+)?" + _DEVERBAL_NIE + r"\b"
         r"|\bоказ\w+\s+(?:помощь|поддержку|содействие|влияние)\b"
         r"|\b" + _GIVE_VERB + r"\s+(?:оценку|согласие|разрешение)\b", re.I),
     "Действие спрятано в существительное. Используй глагол: «проверить», а не «провести проверку»."),
    ("passive-voice", "advisory",
     re.compile(
         r"\b(?:был|была|было|были|будет|будут)\s+\w{3,}(?:ан|ян|ен|ён|ин|т)(?:а|о|ы)?\b"
         r"|\b(?!явля)\w+(?:ется|ются|ится|ятся|ался|алась|алось|ались|ился|илась|илось|ились)"
         r"\s+\w+(?:ом|ем|ём|ами|ями)\b", re.I),
     "Возможен страдательный залог. Назови исполнителя и используй действительный залог, "
     "если исполнитель известен и важен."),
    ("verbose-copula", "advisory",
     re.compile(r"\bявля(?:ется|ются|лся|лась|лось|лись|ться|ющ\w*)\b", re.I),
     "«Является» удлиняет фразу. Используй тире, «это» или точный глагол."),
    ("double-negation", "advisory",
     re.compile(r"\bне\s+(?:мо[жг]\w*|следует|стоит|удастся)\s+не\b|\bнельзя\s+не\b", re.I),
     "Двойное отрицание. Сформулируй утверждение прямо."),
]

# Одно слово — одно значение: глаголы, которые часто чередуют для одного
# действия. Каждый элемент — (имя для сообщения, шаблон основы). Шаблоны
# исключают известные омонимы: «удалённый» (remote), «удалось», «достаточно».
SYNONYM_GROUPS = [
    (("проверить", r"провер\w*"),
     ("удостовериться", r"удостовер\w*"),
     ("верифицировать", r"верифи\w*"),
     ("валидировать", r"валид(?:ир|ац)\w*")),
    (("удалить", r"удал(?![её]нн|ос)\w*"),
     ("стереть", r"(?:стереть|стёр\w*|стер(?:ла|ли|ло)\b|стира\w*)"),
     ("убрать", r"(?:убра\w*|убир\w*|убер(?:и|ите|ёт|ет|ут|у)\b)")),
    (("запустить", r"запу[сщ]\w*"),
     ("стартовать", r"(?:стартова\w*|стартую\w*|стартует|стартуют|стартану\w*)"),
     ("инициировать", r"иницииров\w*")),
    (("остановить", r"останов\w*"),
     ("прекратить", r"(?:прекрат\w*|прекращ\w*)"),
     ("терминировать", r"терминир\w*")),
    (("показать", r"(?:показ\w*|покаж\w*)"),
     ("отобразить", r"(?:отобра\w*|отображ\w*)")),
    (("использовать", r"использ\w*"),
     ("задействовать", r"задейств\w*"),
     ("употребить", r"употреб\w*")),
    (("исправить", r"исправ\w*"),
     ("починить", r"почин(?:ить|и|ите|ил|ила|или|ю|ит|ят)\b"),
     ("пофиксить", r"(?:пофикс\w*|фикс(?:ить|ит|ят|ил|ила|или)\b)")),
    (("отправить", r"отправ\w*"),
     ("послать", r"(?:посыл\w*|посла(?:ть|л|ла|ли|но|ны)\b|пошл(?:и|ите|ёт|ет|ют|ю|ём)\b)")),
    (("получить", r"получ(?!ател)\w*"),
     ("извлечь", r"(?:извлек\w*|извлеч\w*)")),
    (("изменить", r"измен\w*"),
     ("модифицировать", r"модифи\w*"),
     ("поменять", r"поменя\w*")),
]
_SYNONYM_RES = [[(name, re.compile(r"\b" + stem, re.I)) for name, stem in group]
                for group in SYNONYM_GROUPS]

# Лимит для описаний. Лимит инструкций (18 слов) без контекста не определить.
MAX_WORDS = 22

CODE_FENCE = re.compile(r"^(```|~~~)")
INLINE_CODE = re.compile(r"`[^`]*`")
LIST_ITEM_START = re.compile(
    r"^(?P<indent> {0,3})(?P<marker>[-*+]|[0-9]+[.)])(?P<gap> +)(?P<body>.*)$"
)
CONJUNCTION_END = re.compile(r"\b(?:и|или|а|но|либо)\s*$", re.I)
TABLE_SEPARATOR_CELL = re.compile(r"^:?-{3,}:?$")
# Заголовки, горизонтальные линии, разделители front matter и HTML — отдельные блоки.
STANDALONE_LINE = re.compile(r"^ {0,3}(?:#|<|(?:[-*_=] *){3,}$)")
BLOCKQUOTE_PREFIX = re.compile(r"^ {0,3}(?:> ?)+")
# Маркер списка любой глубины начинает новый блок прозы.
ANY_LIST_ITEM = re.compile(r"^\s*(?:[-*+]|[0-9]+[.)])(?:\s|$)")
# Слово с завершающим знаком, после которого могут идти закрывающие кавычки,
# скобки или маркеры выделения Markdown («**Итог.**»).
SENTENCE_END = re.compile(r"(?:[.!?…]|\.\.\.)[\"'”’»)\]*_]*$")
OPENERS = "\"'“‘«([*_"
# Сокращения, точка которых никогда не завершает предложение.
ABBREVIATIONS = {
    "см.", "напр.", "ср.", "рис.", "стр.", "ст.", "гл.", "табл.", "прим.",
    "англ.", "тыс.", "млн.", "млрд.", "руб.", "шт.", "мин.", "сек.", "пп.",
    "vs.", "cf.", "approx.", "fig.", "no.",
}
# Однобуквенные и составные сокращения («т. е.», «т.к.», «e.g.») завершают
# предложение, только если следующее слово начинается с заглавной буквы.
DOTTED_ABBREVIATION = re.compile(r"(?:[a-zа-яё]\.)+", re.I)
# Слово — токен, в котором есть буква или цифра. Тире и знаки — не слова.
WORD = re.compile(r"\w")


def _count_words(text):
    return sum(1 for token in text.split() if WORD.search(token))


def _mask_inline_code(text):
    """Заменить фрагменты кода пробелами той же длины, чтобы колонки совпадали."""
    return INLINE_CODE.sub(lambda match: " " * len(match.group(0)), text)


def _sentence_starts(text):
    """Вернуть смещение начала каждого предложения.

    Предложение заканчивается на слове с завершающим знаком, после
    закрывающих кавычек или скобок. Известные сокращения предложение не
    завершают. Один проход по словам — линейная сложность.
    """
    words = list(re.finditer(r"\S+", text))
    if not words:
        return [0]
    starts = [words[0].start()]
    for word, next_word in zip(words, words[1:]):
        end = SENTENCE_END.search(word.group())
        if not end:
            continue
        core = word.group()[:end.start() + 1].lstrip(OPENERS)
        if core.lower() in ABBREVIATIONS:
            continue
        if (DOTTED_ABBREVIATION.fullmatch(core)
                and not next_word.group().lstrip(OPENERS)[:1].isupper()):
            continue
        starts.append(next_word.start())
    return starts


def _long_sentence_findings(pieces, filename):
    """Отметить длинные предложения в одном блоке прозы.

    pieces — список кортежей (lineno, source_column, text). Тексты
    соединяются пробелом, поэтому перенесённое предложение считается один раз,
    а находка указывает на строку и колонку его начала.
    """
    offsets, position = [], 0
    for _, _, text in pieces:
        offsets.append(position)
        position += len(text) + 1
    joined = " ".join(text for _, _, text in pieces)
    findings = []
    starts = _sentence_starts(joined)
    for start, end in zip(starts, starts[1:] + [len(joined)]):
        n = _count_words(joined[start:end])
        if n <= MAX_WORDS:
            continue
        index = bisect.bisect_right(offsets, start) - 1
        offset = offsets[index]
        lineno, source_column, _ = pieces[index]
        findings.append({"file": filename, "line": lineno,
                         "col": source_column + start - offset + 1,
                         "rule": "long-sentence", "level": "advisory-free",
                         "match": f"{n} слов",
                         "message": f"В предложении {n} слов (лимит {MAX_WORDS}). Раздели его."})
    return findings


def _leading_spaces(line):
    return len(line) - len(line.lstrip(" "))


def _is_list_continuation(line, content_indent):
    if not line.strip():
        return True
    if LIST_ITEM_START.match(line):
        return False
    return _leading_spaces(line) >= content_indent


def _split_table_row(line):
    """Вернуть ячейки строки таблицы и их колонки (с нуля).

    Вертикальная черта должна разделять минимум две ячейки. Экранированная
    черта остаётся в ячейке. Поддержан только обычный вид таблицы Markdown:
    этого хватает, чтобы отличить таблицу от прозы с символом «|».
    """
    left = len(line) - len(line.lstrip())
    right = len(line.rstrip())
    content = line[left:right]
    if "|" not in content:
        return None
    if content.startswith("|"):
        content = content[1:]
        left += 1
    if content.endswith("|"):
        content = content[:-1]
    raw_cells = re.split(r"(?<!\\)\|", content)
    if len(raw_cells) < 2:
        return None

    cells = []
    column = left
    for raw_cell in raw_cells:
        leading = len(raw_cell) - len(raw_cell.lstrip())
        cells.append((raw_cell.strip(), column + leading))
        column += len(raw_cell) + 1
    return cells


def _markdown_table_cells(lines):
    """Сопоставить строки таблиц Markdown с их ячейками.

    Опора — строка-разделитель, поэтому проза с «|» не считается таблицей.
    Принимаются таблицы с ведущей чертой и без неё, если число ячеек в
    заголовке и теле совпадает.
    """
    table_cells = {}
    index = 1
    while index < len(lines):
        separator = _split_table_row(lines[index])
        header = _split_table_row(lines[index - 1])
        if (not separator or not header or len(separator) != len(header)
                or not all(TABLE_SEPARATOR_CELL.fullmatch(cell)
                           for cell, _ in separator)):
            index += 1
            continue

        table_cells[index - 1] = header
        table_cells[index] = []
        index += 1
        while index < len(lines):
            row = _split_table_row(lines[index])
            if not row or len(row) != len(separator):
                break
            table_cells[index] = row
            index += 1
    return table_cells


def _dangling_conjunction_findings(text, filename):
    lines = text.splitlines()
    findings = []
    in_fence = False
    index = 0
    while index < len(lines):
        line = lines[index]
        stripped = line.strip()
        if CODE_FENCE.match(stripped):
            in_fence = not in_fence
            index += 1
            continue
        if in_fence:
            index += 1
            continue
        start = LIST_ITEM_START.match(line)
        if not start:
            index += 1
            continue

        content_indent = (len(start.group("indent"))
                          + len(start.group("marker"))
                          + len(start.group("gap")))
        item_lines = [(index, start.group("body"))]
        next_index = index + 1
        item_fence = False
        while next_index < len(lines):
            candidate = lines[next_index]
            candidate_stripped = candidate.strip()
            if CODE_FENCE.match(candidate_stripped):
                # Ограничители кода меняют состояние, но не являются строками пункта.
                item_fence = not item_fence
                next_index += 1
                continue
            if item_fence:
                next_index += 1
                continue
            if not _is_list_continuation(candidate, content_indent):
                break
            item_lines.append((next_index, candidate))
            next_index += 1

        meaningful = []
        for line_index, item_line in item_lines:
            # Фрагмент кода — нейтральный операнд, его содержимое не проверяется.
            cleaned = INLINE_CODE.sub(" CODE ", item_line).strip()
            if cleaned:
                meaningful.append((line_index, cleaned))
        if meaningful:
            end_line_index, end_line = meaningful[-1]
            conjunction = CONJUNCTION_END.search(end_line)
        else:
            end_line_index, end_line, conjunction = None, None, None
        if conjunction:
            if end_line_index == index:
                finding_line = index + 1
                finding_col = start.start("marker") + 1
            else:
                raw_end_line = next(
                    raw for line_index, raw in item_lines
                    if line_index == end_line_index
                )
                masked_end_line = INLINE_CODE.sub(
                    lambda match: " " * len(match.group(0)), raw_end_line
                )
                raw_conjunction = CONJUNCTION_END.search(masked_end_line)
                finding_line = end_line_index + 1
                finding_col = raw_conjunction.start() + 1 if raw_conjunction else 1
            findings.append({
                "file": filename,
                "line": finding_line,
                "col": finding_col,
                "rule": "dangling-conjunction",
                "level": "advisory-free",
                "match": end_line,
                "message": "Пункт списка заканчивается союзом. Допиши пункт или объедини его со следующим.",
            })
        index = next_index
    return findings


def lint(text, filename="<stdin>"):
    findings = []
    words_total = 0
    in_fence = False
    lines = text.splitlines()
    table_cells = _markdown_table_cells(lines)
    # первое вхождение каждого синонима: (group_idx, name) -> (line, col, match)
    seen_synonyms = {}
    # соседние строки прозы — один блок, перенесённое предложение считается один раз
    block = []
    in_quote = False

    def flush():
        findings.extend(_long_sentence_findings(block, filename))
        block.clear()

    for lineno, raw_line in enumerate(lines, 1):
        if CODE_FENCE.match(raw_line.strip()):
            flush()
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        segments = table_cells.get(lineno - 1, [(raw_line, 0)])
        is_table = (lineno - 1) in table_cells
        quote = BLOCKQUOTE_PREFIX.match(raw_line)
        is_quote = bool(quote)
        # границы блока определяются по тексту внутри префикса цитаты
        content = raw_line[quote.end():] if quote else raw_line
        standalone = STANDALONE_LINE.match(content)
        if (is_table or not content.strip() or standalone
                or ANY_LIST_ITEM.match(content) or is_quote != in_quote):
            flush()
        in_quote = is_quote
        for segment, source_column in segments:
            line = _mask_inline_code(segment)
            words_total += _count_words(line)
            for rule_id, level, pattern, msg in RULES:
                for m in pattern.finditer(line):
                    findings.append({"file": filename, "line": lineno,
                                     "col": source_column + m.start() + 1,
                                     "rule": rule_id, "level": level,
                                     "match": m.group(0), "message": msg})
            for gi, group in enumerate(_SYNONYM_RES):
                for name, pattern in group:
                    if (gi, name) in seen_synonyms:
                        continue
                    m = pattern.search(line)
                    if m:
                        seen_synonyms[(gi, name)] = (
                            lineno, source_column + m.start() + 1, m.group(0)
                        )
            # префикс цитаты — разметка, а не слова предложения
            skip = quote.end() if quote and not is_table else 0
            if line[skip:].strip():
                block.append((lineno, source_column + skip, line[skip:]))
            if is_table:
                flush()  # каждая ячейка таблицы — отдельный блок
        if standalone:
            flush()
    flush()
    # чередование синонимов: отметить каждый вариант после первого, в месте первого появления
    for gi, group in enumerate(_SYNONYM_RES):
        present = [(seen_synonyms[(gi, name)], name) for name, _ in group
                   if (gi, name) in seen_synonyms]
        if len(present) > 1:
            present.sort()  # порядок документа
            first_name = present[0][1]
            for (lineno, col, match), name in present[1:]:
                findings.append({"file": filename, "line": lineno, "col": col,
                                 "rule": "synonym-rotation", "level": "advisory-free",
                                 "match": match,
                                 "message": f"«{name}» и «{first_name}» называют одно действие. "
                                            "Выбери одно слово и используй его везде."})
    findings.extend(_dangling_conjunction_findings(text, filename))
    findings.sort(key=lambda f: (f["line"], f["col"]))
    return findings, words_total


def report(findings, words_total, as_json, hard_count, baseline):
    rate = round(len(findings) * 100 / words_total, 1) if words_total else 0.0
    if as_json:
        print(json.dumps({"violations": findings, "count": len(findings),
                          "hard_count": hard_count, "baseline": baseline,
                          "words": words_total, "per_100_words": rate},
                         indent=2, ensure_ascii=False))
        return
    for f in findings:
        print(f"{f['file']}:{f['line']}:{f['col']} {f['rule']}: {f['message']} [{f['match']}]")
    print(f"\nНарушений: {len(findings)} (жёстких {hard_count}, базовая линия {baseline}), "
          f"слов: {words_total}, на 100 слов: {rate}")
    print("Модальность (может, мог, возможно, вероятно) не отмечается: уверенность — это содержание.")


def _rules(text):
    findings, _ = lint(text)
    return [f["rule"] for f in findings]


def selftest():
    bad = ("Панель была снята; пофиксить баг. "
           "Провести анализ бесшовного лога. "
           "В целях проверки модуль является главным. "
           "Нельзя не отметить это.")
    rules = set(_rules(bad))
    for expected in ("semicolon", "jargon-verb", "nominalization", "marketing-adjective",
                     "bureaucratese", "passive-voice", "verbose-copula", "double-negation"):
        assert expected in rules, (expected, rules)
    # модальность никогда не отмечается
    findings, _ = lint("Запрос мог не выполниться. Возможно, это тайм-аут. "
                       "Вероятно, диск заполнился. Сервер может вернуть ошибку.")
    assert findings == [], findings
    # отглагольные существительные
    for text in ("Выполните удаление файла.", "Сервис произвёл перезагрузку.",
                 "Провести полную проверку конфигурации.", "Провести анализ лога.",
                 "Оказать поддержку команде.", "Дать оценку задаче."):
        assert "nominalization" in _rules(text), text
    for text in ("Выполните команду установки.", "Выполните миграцию.",
                 "Проверьте конфигурацию.", "Провод подключён к порту."):
        assert "nominalization" not in _rules(text), text
    # канцелярит
    for text in ("В случае если файл пуст, выйти.", "Доступ осуществляется через API.",
                 "Связь посредством очереди.", "В связи с тем, что сервер упал."):
        assert "bureaucratese" in _rules(text), text
    # жаргонные глаголы и их ложные срабатывания
    for text in ("Надо пофиксить тест.", "Заапрувь PR.", "Засетапить окружение.",
                 "Юзать кэш.", "Задеплоить на стенд."):
        assert "jargon-verb" in _rules(text), text
    assert "jargon-verb" not in _rules("Пошаговая инструкция. Фикстура теста.")
    # рекламные слова и технические омонимы
    assert "marketing-adjective" in _rules("Мощный и бесшовный инструмент.")
    assert "marketing-adjective" not in _rules("Мощность блока питания. Уникальный индекс.")
    # страдательный залог
    for text in ("Файл был удалён.", "Отчёт будет создан.", "Запросы были отправлены.",
                 "Файл удаляется сервером."):
        assert "passive-voice" in _rules(text), text
    for text in ("Это было важно.", "Сервер будет работать.", "Файл хранится в памяти.",
                 "Ответ является советом."):
        assert "passive-voice" not in _rules(text), text
    # двойное отрицание
    assert "double-negation" in _rules("Сервис не может не ответить.")
    assert "double-negation" not in _rules("Сервис не может ответить. Ничего не найдено.")
    # блоки кода пропускаются
    findings, _ = lint("```\nx = a; y = b\n```")
    assert findings == [], findings
    # все поддержанные маркеры списка, регистр и пробелы в конце
    findings, _ = lint(
        "- Проверь цель и\n"
        "* Запиши результат ИЛИ  \n"
        "+ Закрой панель\n"
        "1. Запусти задачу а\n"
        "2) Останови задачу либо"
    )
    dangling = [f for f in findings if f["rule"] == "dangling-conjunction"]
    assert [f["line"] for f in dangling] == [1, 2, 4, 5], dangling
    assert [f["col"] for f in dangling] == [1, 1, 1, 1], dangling
    assert all(f["level"] == "advisory-free" for f in dangling), dangling
    # продолжение пункта и отдельный код с отступом четыре пробела
    assert "dangling-conjunction" not in _rules("  - Проверь цель и\n    запиши результат.")
    findings, _ = lint("- Проверь цель\n  и")
    dangling = [f for f in findings if f["rule"] == "dangling-conjunction"]
    assert len(dangling) == 1 and (dangling[0]["line"], dangling[0]["col"]) == (2, 3), dangling
    assert "dangling-conjunction" not in _rules("    - код и")
    assert "dangling-conjunction" not in _rules("> - Проверь цель и\n> - Запиши итог или")
    assert "dangling-conjunction" not in _rules("- Используй `и` как метку")
    assert "dangling-conjunction" not in _rules("- Запусти задачу и.\n- Останови задачу или,")
    assert "dangling-conjunction" not in _rules("Процесс может включать шаги и")
    findings, _ = lint("- Пункт и\n~~~\nкод и\n~~~")
    dangling = [f for f in findings if f["rule"] == "dangling-conjunction"]
    assert len(dangling) == 1 and dangling[0]["line"] == 1, dangling
    # длинные предложения: тире и знаки не считаются словами
    assert "long-sentence" in _rules(("слово " * 25).strip() + ".")
    assert "long-sentence" not in _rules(" — ".join(["слово"] * 22) + ".")
    twenty = " ".join(["слово"] * 20)
    # русские сокращения не завершают предложение, а «т. е.» — только перед заглавной
    assert "long-sentence" in _rules(f"Используй инструмент, напр. {twenty} сейчас.")
    assert "long-sentence" in _rules(f"Сервер упал, т. е. {twenty} вчера.")
    assert "long-sentence" not in _rules(f"Это файлы, логи и т. д. Затем {twenty} вчера.")
    # предложение заканчивается после закрывающих кавычек и многоточия
    assert "long-sentence" not in _rules(f"Он спросил «{twenty}?» Затем {twenty}… Дальше.")
    # таблица Markdown: каждая ячейка — отдельный блок
    short_cell = " ".join(f"слово{n}" for n in range(1, 21)) + "."
    findings, words_total = lint(f"| Метка | Текст |\n| --- | --- |\n| Ясно | {short_cell} |")
    assert "long-sentence" not in [f["rule"] for f in findings], findings
    assert words_total == 23, words_total
    long_cell = " ".join(f"слово{n}" for n in range(1, 25)) + "."
    findings, _ = lint(f"| Метка | Текст |\n| --- | --- |\n| Ясно | {long_cell} |")
    long_sentences = [f for f in findings if f["rule"] == "long-sentence"]
    assert len(long_sentences) == 1 and long_sentences[0]["match"] == "24 слов", long_sentences
    # перенесённое предложение считается один раз, в месте начала
    findings, _ = lint(f"Вступление.\nЭто {twenty}\nхвост перенесённой фразы.")
    long_sentences = [f for f in findings if f["rule"] == "long-sentence"]
    assert [(f["line"], f["col"]) for f in long_sentences] == [(2, 1)], long_sentences
    # пустая строка, заголовок, линия, пункт списка и цитата завершают блок
    for sep in ("\n\n", "\n# Заголовок\n", "\n---\n", "\n- ", "\n> "):
        assert "long-sentence" not in _rules(f"Первая {twenty} строка{sep}Вторая {twenty} строка."), sep
    assert "long-sentence" not in _rules(f"**Итог.** Это {twenty} тут.")
    # длинный блок обрабатывается линейно
    assert "long-sentence" not in _rules("Агент прочитал лог.\n" * 20000)
    # чередование синонимов: второй вариант отмечен, первый назван основным
    findings, _ = lint("Проверьте конфиг. Затем удостоверьтесь в выводе. Удостоверьтесь дважды.")
    rot = [f for f in findings if f["rule"] == "synonym-rotation"]
    assert len(rot) == 1 and "«удостовериться» и «проверить»" in rot[0]["message"], rot
    assert "synonym-rotation" not in _rules("Проверьте конфиг. Проверьте вывод.")
    # омонимы не считаются синонимами: «удалённый» (remote), «удалось», «получатель»
    assert "synonym-rotation" not in _rules("Удалённый сервер ответил. Удалось убрать лишнее.")
    assert "synonym-rotation" not in _rules("Получатель — хаб. Извлеките токен.")
    assert "synonym-rotation" in _rules("Удалите файл. Затем уберите каталог.")
    # колонки сохраняются после маскирования кода
    findings, _ = lint("Запусти `make all`, потом пофиксить ноду.")
    jargon = [f for f in findings if f["rule"] == "jargon-verb"]
    assert len(jargon) == 1 and jargon[0]["col"] == 27, jargon
    # имя файла в находках
    findings, _ = lint("a; b", filename="x.md")
    assert findings[0]["file"] == "x.md"
    # флаги можно ставить между путями к файлам
    with tempfile.TemporaryDirectory() as tmp:
        paths = [os.path.join(tmp, name) for name in ("a.md", "b.md")]
        for path in paths:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write("Короткая строка — здесь.\n")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            assert main([paths[0], "--json", paths[1]]) == 0
        assert json.loads(out.getvalue())["words"] == 6, out.getvalue()
    # разбор командной строки отклоняет опечатки и плохие значения
    for bad_args in (["--basline", "3"], ["--baseline"], ["--baseline", "x"],
                     ["--baseline", "-1"], ["--disable", "passive"], ["--base", "3"]):
        try:
            with contextlib.redirect_stderr(io.StringIO()):
                main(bad_args)
        except SystemExit as e:
            assert e.code == 2, (bad_args, e.code)
        else:
            raise AssertionError(bad_args)
    assert _rule_list("passive-voice,verbose-copula") == {"passive-voice", "verbose-copula"}
    print("selftest OK")


RULE_IDS = {rule_id for rule_id, *_ in RULES} | {
    "long-sentence", "synonym-rotation", "dangling-conjunction"}


def _rule_list(value):
    rules = {r for r in value.split(",") if r}
    unknown = rules - RULE_IDS
    if unknown:
        raise argparse.ArgumentTypeError(
            f"неизвестные правила: {', '.join(sorted(unknown))}. "
            f"Известные правила: {', '.join(sorted(RULE_IDS))}")
    return rules


def _non_negative_int(value):
    try:
        n = int(value)
    except ValueError:
        n = -1
    if n < 0:
        raise argparse.ArgumentTypeError(f"нужно неотрицательное целое, получено {value!r}")
    return n


def main(argv):
    parser = argparse.ArgumentParser(
        prog="ste-lint.py", allow_abbrev=False,
        description="Детерминированный линтер структурных правил STE для русского текста. "
                    "Без FILE читает stdin.")
    parser.add_argument("paths", nargs="*", metavar="FILE")
    parser.add_argument("--json", action="store_true", help="вывести находки в JSON")
    parser.add_argument("--baseline", type=_non_negative_int, default=0, metavar="N",
                        help="успех, пока жёстких нарушений не больше N (по умолчанию 0)")
    parser.add_argument("--disable", type=_rule_list, default=set(), metavar="RULES",
                        help="правила через запятую, которые нужно отключить")
    parser.add_argument("--selftest", action="store_true", help="выполнить встроенные тесты")
    # смешанный разбор разрешает флаги между путями
    args = parser.parse_intermixed_args(argv)
    if args.selftest:
        selftest()
        return 0
    as_json, baseline, disabled, paths = args.json, args.baseline, args.disable, args.paths

    findings, words_total = [], 0
    if paths:
        for p in paths:
            try:
                with open(p, encoding="utf-8") as fh:
                    text = fh.read()
            except OSError as e:
                parser.error(f"не удалось прочитать {p}: {e.strerror}")
            f, w = lint(text, filename=p)
            findings.extend(f)
            words_total += w
    else:
        findings, words_total = lint(sys.stdin.read())

    findings = [f for f in findings if f["rule"] not in disabled]
    hard_count = sum(1 for f in findings if f["level"] == "advisory-free")
    report(findings, words_total, as_json, hard_count, baseline)
    return 1 if hard_count > baseline else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
