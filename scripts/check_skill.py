#!/usr/bin/env python3
"""Механическая проверка собранного скилла: то, что нельзя доверить внимательности.

Проверяет: валидность frontmatter, существование маршрутов из SKILL.md,
осиротевшие справочники, дубли нормы между файлами, наличие разделов
«готово» и «можно без вопросов», капсовые императивы без причины,
захардкоженные личные пути и похожие на секреты строки.

Выход: 0 — чисто, 1 — есть находки, 2 — ошибка запуска.
"""
import argparse, itertools, os, re, sys

WORD = re.compile(r"[^\W\d_]+", re.UNICODE)
CAPS = re.compile(r"\b(ВСЕГДА|НИКОГДА|ОБЯЗАТЕЛЬНО|КРИТИЧЕСКИ|NEVER|ALWAYS|MUST)\b")
SECRET = re.compile(r"(sk-[A-Za-z0-9]{12,}|ghp_[A-Za-z0-9]{12,}|xox[bp]-|AKIA[0-9A-Z]{12,})")
HOMEDIR = re.compile(r"(/Users/[a-zA-Z0-9._-]+|/home/[a-zA-Z0-9._-]+)")
WHY = re.compile(r"(потому|так как|причина|иначе|чтобы не|необратим|нельзя отозвать|—\s*\w)")


def norm_words(text):
    text = re.sub(r"```.*?```", " ", text, flags=re.S)          # код не считаем дублем
    return WORD.findall(text.lower())


def shingles(text, n=8):
    w = norm_words(text)
    return {" ".join(w[i:i + n]) for i in range(max(0, len(w) - n + 1))}


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def main():
    ap = argparse.ArgumentParser(description="Проверка собранного скилла перед выдачей автору")
    ap.add_argument("skill_dir", help="директория скилла (та, где лежит SKILL.md)")
    ap.add_argument("--min-shingle", type=int, default=8,
                    help="длина повторяющегося фрагмента в словах, которая считается дублем (по умолчанию 8)")
    ap.add_argument("--skip-sections", action="store_true",
                    help="не требовать разделов «готово» и «можно без вопросов» (для скилла-справочника)")
    a = ap.parse_args()

    root = os.path.abspath(a.skill_dir)
    main_file = os.path.join(root, "SKILL.md")
    if not os.path.isfile(main_file):
        print(f"ОШИБКА: не найден {main_file}", file=sys.stderr)
        return 2

    body = read(main_file)
    problems, notes = [], []

    # 1. frontmatter
    if not body.startswith("---"):
        problems.append("SKILL.md: нет frontmatter")
    else:
        fm = body.split("---", 2)[1]
        if not re.search(r"^\s*description\s*:", fm, re.M):
            notes.append("SKILL.md: нет поля description — модель будет брать первую строку тела")
        name = re.search(r"^\s*name\s*:\s*(\S+)", fm, re.M)
        if name and name.group(1) != os.path.basename(root):
            problems.append(f"SKILL.md: name «{name.group(1)}» не совпадает с именем директории «{os.path.basename(root)}»")

    # 2. маршруты и сироты
    linked = set(re.findall(r"[`(]((?:references|scripts|assets|evals)/[\w./-]+)[`)]", body))
    for rel in sorted(linked):
        if not os.path.exists(os.path.join(root, rel)):
            problems.append(f"SKILL.md ссылается на несуществующий файл: {rel}")
    on_disk = []
    for sub in ("references", "scripts", "assets"):
        d = os.path.join(root, sub)
        if os.path.isdir(d):
            on_disk += [os.path.join(sub, f) for f in sorted(os.listdir(d)) if not f.startswith(".")]
    for rel in on_disk:
        if rel not in linked and rel.endswith(".md"):
            notes.append(f"нет маршрута из SKILL.md: {rel} — его не откроют")

    # 3. дубли нормы между файлами
    files = [main_file] + [os.path.join(root, r) for r in on_disk if r.endswith(".md")]
    texts = {f: read(f) for f in files if os.path.isfile(f)}
    grams = {f: shingles(t, a.min_shingle) for f, t in texts.items()}
    for f1, f2 in itertools.combinations(sorted(grams), 2):
        common = sorted(grams[f1] & grams[f2], key=len, reverse=True)
        if common:
            problems.append(
                f"одна норма в двух файлах: {os.path.relpath(f1, root)} и {os.path.relpath(f2, root)}\n"
                f"      повтор: «{common[0][:90]}…»")

    # 4. обязательные разделы
    if not a.skip_sections:
        low = body.lower()
        if "готово" not in low:
            problems.append("SKILL.md: нет раздела «Готово, когда» — модель остановится на первом варианте")
        if not re.search(r"без вопрос|без спрос|можно без", low):
            problems.append("SKILL.md: нет полки разрешённого — ассистент будет спрашивать про каждую мелочь")

    # 5. капс без причины, личные пути, секреты
    for f, t in texts.items():
        rel = os.path.relpath(f, root)
        for i, line in enumerate(t.splitlines(), 1):
            if CAPS.search(line) and not WHY.search(line):
                notes.append(f"{rel}:{i}: жёсткий императив без причины — «{line.strip()[:70]}»")
            if HOMEDIR.search(line):
                problems.append(f"{rel}:{i}: личный путь — «{HOMEDIR.search(line).group(1)}», нужен ${{CLAUDE_PROJECT_DIR}} или ${{CLAUDE_SKILL_DIR}}")
            if SECRET.search(line):
                problems.append(f"{rel}:{i}: похоже на секрет в тексте скилла")

    for p in problems:
        print(f"  [чинить] {p}")
    for n in notes:
        print(f"  [посмотреть] {n}")
    if not problems and not notes:
        print("  чисто: маршруты на месте, дублей нет, обязательные разделы есть")
    print(f"\nитого: {len(problems)} к починке, {len(notes)} на посмотреть")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
