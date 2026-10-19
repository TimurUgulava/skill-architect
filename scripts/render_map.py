#!/usr/bin/env python3
"""Живая карта работы архитектора: карта.json → карта.html.

Страница самодостаточна (ни одного внешнего запроса, кроме шрифтов с
запасным вариантом), обновляется сама каждые две секунды и работает
с file:// без сервера. Архитектор правит карта.json и запускает рендер;
человек держит страницу открытой и видит, что происходит.

Использование:
  render_map.py <папка с карта.json> [--open] [--title "…"] [--example]

  --open     открыть карта.html в браузере (macOS open / Linux xdg-open)
  --example  записать в папку образец карта.json, если файла ещё нет
  --title    переопределить заголовок карты

Форма карта.json (все поля необязательны, кроме title):
  title      название будущего скилла
  step       0–6, шаг архитектора: нужен ли → разобраться → договориться →
             устройство → собрать → проверить → отдать
  now        одно предложение: что архитектор делает прямо сейчас
  stages     [{who, text, status}] — карта работы будущего скилла;
             who ∈ человек | скилл | стоп | выход | дальше
             status ∈ confirmed | assumed | unknown
  services   [{name, need, access, how}] — внешние сервисы;
             access ∈ yes | no | unknown
  done_when  [строки]       allowed [строки]       forbidden [строки]
  log        [{t, text, who}] — журнал; who = "человек" для дословных ответов

Выход: 0 — карта записана, 1 — ошибка в карта.json, 2 — файл не найден.
"""
import argparse
import datetime
import html
import json
import os
import subprocess
import sys

STEPS = ["нужен ли", "разобраться", "договориться", "устройство",
         "собрать", "проверить", "отдать"]
WHO = ("человек", "скилл", "стоп", "выход", "дальше")
STATUS = ("confirmed", "assumed", "unknown")
ACCESS = ("yes", "no", "unknown")

EXAMPLE = {
    "title": "Название будущего скилла",
    "step": 1,
    "now": "читаю соседние скиллы проекта, ищу пересечение триггеров",
    "stages": [
        {"who": "человек", "text": "с чего начинается работа", "status": "unknown"},
        {"who": "скилл", "text": "что скилл делает сам", "status": "unknown"},
        {"who": "стоп", "text": "где останавливается и спрашивает", "status": "unknown"},
        {"who": "выход", "text": "что получается и куда ложится", "status": "unknown"},
        {"who": "дальше", "text": "кто это читает и что делает потом", "status": "unknown"},
    ],
    "services": [],
    "done_when": [],
    "allowed": [],
    "forbidden": [],
    "log": [],
}


def fail(msg, code=1):
    print("render_map: " + msg, file=sys.stderr)
    sys.exit(code)


def check(data):
    if not isinstance(data, dict) or not data.get("title"):
        fail("в карта.json нет поля title")
    step = data.get("step", 0)
    if not isinstance(step, int) or not 0 <= step <= 6:
        fail("step должен быть целым от 0 до 6, сейчас %r" % (step,))
    for i, s in enumerate(data.get("stages", [])):
        if s.get("who") not in WHO:
            fail("stages[%d].who = %r, допустимо: %s" % (i, s.get("who"), ", ".join(WHO)))
        if s.get("status", "confirmed") not in STATUS:
            fail("stages[%d].status = %r, допустимо: %s" % (i, s.get("status"), ", ".join(STATUS)))
        if not s.get("text"):
            fail("stages[%d] без text" % i)
    for i, s in enumerate(data.get("services", [])):
        if not s.get("name"):
            fail("services[%d] без name" % i)
        if s.get("access", "unknown") not in ACCESS:
            fail("services[%d].access = %r, допустимо: %s" % (i, s.get("access"), ", ".join(ACCESS)))
    for key in ("done_when", "allowed", "forbidden"):
        if not isinstance(data.get(key, []), list):
            fail("%s должен быть списком строк" % key)


def e(s):
    return html.escape(str(s), quote=True)


CSS = """
@import url('https://fonts.googleapis.com/css2?family=Geist:wght@400;500;600&display=swap');
:root{--n1:oklch(98.5% 0.004 80);--n2:oklch(97% 0.004 80);--n3:oklch(94.5% 0.005 80);--n5:oklch(86% 0.007 80);--n6:oklch(76% 0.008 80);--n7:oklch(62% 0.009 80);--n8:oklch(40% 0.01 80);--n9:oklch(49% 0.01 80);--n10:oklch(22% 0.01 80);
 --surface:oklch(99.6% 0.002 80);--line:oklch(22% 0.01 80 / .08);--shadow:0 1px 2px oklch(30% 0.02 80 / .05),0 12px 32px -16px oklch(30% 0.02 80 / .14);
 --accent:oklch(52% 0.19 262);--accent-soft:oklch(52% 0.19 262 / .08);--gold:oklch(56% 0.12 82);--gold-soft:oklch(56% 0.12 82 / .12);--bad:oklch(60% 0.17 28);--bad-soft:oklch(60% 0.17 28 / .1);--done:oklch(60% 0.14 155);--done-soft:oklch(60% 0.14 155 / .12);--moved:oklch(70% 0.15 70);--moved-ink:oklch(52% 0.13 65);--moved-soft:oklch(70% 0.15 70 / .16);
 --spot1:oklch(86% 0.08 45);--spot2:oklch(85% 0.07 275);--spot-op:.4;--font:"Geist",system-ui,-apple-system,sans-serif;--r-m:10px;--r-l:16px}
@media(prefers-color-scheme:dark){:root{--n1:oklch(17% 0.005 80);--n2:oklch(20% 0.006 80);--n3:oklch(23.5% 0.006 80);--n5:oklch(32% 0.008 80);--n6:oklch(44% 0.008 80);--n7:oklch(58% 0.009 80);--n8:oklch(82% 0.007 80);--n9:oklch(70% 0.008 80);--n10:oklch(93% 0.005 80);
 --surface:oklch(20.5% 0.006 80);--line:oklch(93% 0.005 80 / .09);--shadow:0 1px 0 oklch(100% 0 0 / .03) inset,0 12px 32px -18px oklch(0% 0 0 / .6);
 --accent:oklch(72% 0.14 262);--accent-soft:oklch(72% 0.14 262 / .14);--gold:oklch(83% 0.12 88);--gold-soft:oklch(83% 0.12 88 / .14);--bad:oklch(70% 0.14 28);--bad-soft:oklch(70% 0.14 28 / .14);--done:oklch(72% 0.13 155);--done-soft:oklch(72% 0.13 155 / .14);--moved:oklch(78% 0.13 70);--moved-ink:oklch(80% 0.11 70);--moved-soft:oklch(78% 0.13 70 / .16);
 --spot1:oklch(38% 0.07 45);--spot2:oklch(36% 0.07 275);--spot-op:.35;color-scheme:dark}}
*{box-sizing:border-box}
body{margin:0;background:var(--n1);color:var(--n10);font-family:var(--font);font-size:15px;line-height:22px;font-variant-numeric:tabular-nums}
body:before{content:"";position:fixed;inset:0;z-index:-1;background:radial-gradient(60% 40% at 15% 0%,var(--spot1),transparent 70%),radial-gradient(50% 40% at 90% 0%,var(--spot2),transparent 70%);opacity:var(--spot-op);pointer-events:none}
.wrap{max-width:1080px;margin:0 auto;padding:36px 24px 48px}
.head{display:flex;flex-wrap:wrap;align-items:baseline;justify-content:space-between;gap:8px 16px}
h1{font-size:30px;line-height:36px;font-weight:600;margin:0;letter-spacing:-.01em}
h1 small{display:block;font-size:13px;line-height:18px;font-weight:500;color:var(--n9);letter-spacing:0}
.chips{display:flex;gap:8px;flex-wrap:wrap}
.chip{display:inline-flex;align-items:center;gap:8px;padding:3px 10px;border-radius:999px;background:var(--n2);border:1px solid var(--line);font-size:13px;line-height:18px;color:var(--n9)}
.chip i{width:8px;height:8px;border-radius:50%;background:var(--n6)}
.chip.live i{background:var(--done)}
.panel{background:var(--surface);border:1px solid var(--line);border-radius:var(--r-l);box-shadow:var(--shadow)}
.summary{margin-top:22px;display:grid;grid-template-columns:1.1fr 1.6fr 1.3fr}
.summary>div{padding:20px 22px}
.summary>div+div{border-left:1px solid var(--line)}
@media(max-width:860px){.summary{grid-template-columns:1fr}.summary>div+div{border-left:0;border-top:1px solid var(--line)}}
.lbl{font-size:13px;line-height:18px;color:var(--n9);margin-bottom:10px}
.big{font-size:26px;line-height:32px;font-weight:600}
.big span{font-size:15px;font-weight:400;color:var(--n9);margin-left:6px}
.steps{display:flex;gap:3px;margin:10px 0 8px}
.steps b{flex:1;height:8px;border-radius:3px;background:var(--n4,var(--n3))}
.steps b.done{background:var(--done)} .steps b.cur{background:var(--accent)}
.steps-lbl{font-size:12px;line-height:16px;color:var(--n9)}
.now{font-size:17px;line-height:24px;font-weight:500}
.now .cursor{display:inline-block;width:7px;height:17px;background:var(--accent);vertical-align:-2px;margin-left:3px;animation:blink 1s steps(2) infinite}
@keyframes blink{to{opacity:0}}
.open{font-size:14px;line-height:20px;color:var(--n8)}
.open div{display:flex;gap:8px;align-items:baseline;margin:2px 0}
.open i{flex:none;width:8px;height:8px;border-radius:50%;background:var(--moved);position:relative;top:-1px}
.open i.bad{background:var(--bad)}
.none{color:var(--n7)}
h2{font-size:17px;line-height:24px;font-weight:600;margin:28px 0 10px}
h3{font-size:13px;line-height:18px;font-weight:600;color:var(--n9);margin:0 0 8px}
/* процесс */
.rows{padding:4px 0}
.row{display:grid;grid-template-columns:28px 120px 1fr;gap:12px;align-items:baseline;padding:11px 20px;border-top:1px solid var(--line)}
.row:first-child{border-top:0}
.st{display:inline-block;width:10px;height:10px;border-radius:50%;background:var(--done);position:relative;top:0;margin-left:8px}
.st.ring{background:transparent;border:2px solid var(--moved);width:10px;height:10px;box-sizing:border-box}
.st.ghost{background:transparent;border:2px solid var(--n5);box-sizing:border-box}
.st.dia{border-radius:2px;transform:rotate(45deg);background:var(--gold);width:9px;height:9px}
.row .who{font-size:13px;line-height:18px;color:var(--n9)}
.row .txt{font-size:15px}
.row.stop .txt{font-weight:500}.row.stop .who{color:var(--gold)}
.row.unknown .txt{color:var(--n7)}
.row .mark{margin-left:10px;font-size:12px;line-height:16px;color:var(--moved-ink);background:var(--moved-soft);padding:1px 8px;border-radius:999px;white-space:nowrap}
.row.unknown .mark{color:var(--n9);background:var(--n3)}
/* две панели */
.two{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-top:16px}
@media(max-width:860px){.two{grid-template-columns:1fr}}
.two .panel{padding:18px 20px}
.svc{display:grid;grid-template-columns:1fr auto;gap:8px 12px;align-items:center}
.svc .n{font-weight:500}
.svc .need{display:block;font-size:13px;line-height:18px;color:var(--n9);font-weight:400}
.svc .how{grid-column:1/-1;font-size:13px;line-height:18px;color:var(--n9);margin:-4px 0 2px;padding-left:12px;border-left:2px solid var(--line)}
.pill{font-size:12px;line-height:16px;padding:3px 9px;border-radius:999px;white-space:nowrap;font-weight:500}
.pill.yes{background:var(--done-soft);color:var(--done)} .pill.no{background:var(--bad-soft);color:var(--bad)} .pill.unknown{background:var(--moved-soft);color:var(--moved-ink)}
ul{margin:0;padding-left:18px;font-size:14px;line-height:20px} li{margin:4px 0}
li::marker{color:var(--n6)}
.shelves{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-top:16px}
.shelves h3.ok{color:var(--done)} .shelves h3.no{color:var(--bad)}
.empty{color:var(--n7);font-size:14px;line-height:20px}
/* журнал */
.log{margin-top:20px;padding:14px 20px;display:grid;grid-template-columns:auto 1fr;gap:3px 14px;font-size:13px;line-height:18px;color:var(--n9)}
.log .t{color:var(--n7)}
.log .q{color:var(--n10)} .log .q:before{content:"«"} .log .q:after{content:"»"}
footer{margin-top:14px;color:var(--n7);font-size:12px;line-height:16px}
"""


def render(data, title=None):
    title = title or data["title"]
    step = data.get("step", 0)
    now = data.get("now") or ""
    stages = data.get("stages", [])
    svcs = data.get("services", [])
    out = []
    a = out.append
    a("<!doctype html><html lang='ru'><head><meta charset='utf-8'>")
    a("<meta http-equiv='refresh' content='2'>")
    a("<meta name='viewport' content='width=device-width,initial-scale=1'>")
    a("<title>%s · карта работы</title><style>%s</style></head><body><div class='wrap'>" % (e(title), CSS))
    a("<div class='head'><h1><small>Карта работы</small>%s</h1><div class='chips'>"
      "<span class='chip live'><i></i>Снимок %s</span></div></div>"
      % (e(title), datetime.datetime.now().strftime("%H:%M:%S")))
    # сводка
    a("<div class='panel summary'>")
    a("<div><div class='lbl'>Шаг архитектора</div><div class='big'>%d<span>из 7 · %s</span></div><div class='steps'>" % (step + 1, e(STEPS[step])))
    for i in range(7):
        a("<b class='%s'></b>" % ("done" if i < step else ("cur" if i == step else "")))
    a("</div><div class='steps-lbl'>%s</div></div>" % e(" · ".join(STEPS[max(0, step - 1):step + 2])))
    a("<div><div class='lbl'>Сейчас</div><div class='now'>%s<span class='cursor'></span></div></div>"
      % (e(now) if now else "<span class='none'>жду ответа</span>"))
    opens = []
    for sv in svcs:
        acc = sv.get("access", "unknown")
        if acc == "no":
            opens.append(("bad", "%s: доступа нет" % sv["name"]))
        elif acc == "unknown":
            opens.append(("", "%s: доступ не выяснен" % sv["name"]))
    for st in stages:
        if st.get("status") == "assumed":
            opens.append(("", "предположение: %s" % st["text"]))
    unknown = sum(1 for st in stages if st.get("status") == "unknown")
    if unknown:
        opens.append(("", "ещё не обсуждали: %d" % unknown))
    a("<div><div class='lbl'>Открытые вопросы</div><div class='open'>")
    if opens:
        for cls, text in opens[:5]:
            a("<div><i class='%s'></i>%s</div>" % (cls, e(text)))
        if len(opens) > 5:
            a("<div class='none'>и ещё %d</div>" % (len(opens) - 5))
    else:
        a("<span class='none'>нет</span>")
    a("</div></div></div>")
    # процесс
    a("<h2>Как пойдёт работа скилла</h2><div class='panel rows'>")
    if not stages:
        a("<div class='row'><span></span><span class='who'></span><span class='empty'>карта ещё пустая: первый раунд вопросов впереди</span></div>")
    for st in stages:
        status = st.get("status", "confirmed")
        who = st["who"]
        shape = "dia" if who == "стоп" else {"assumed": "ring", "unknown": "ghost"}.get(status, "")
        label = "остановка" if who == "стоп" else who
        mark = {"assumed": "<span class='mark'>предположение</span>", "unknown": "<span class='mark'>не обсуждали</span>"}.get(status, "")
        a("<div class='row %s %s'><span class='st %s'></span><span class='who'>%s</span><span class='txt'>%s%s</span></div>"
          % (status, "stop" if who == "стоп" else "", shape, e(label), e(st["text"]), mark))
    a("</div>")
    # две панели
    a("<div class='two'><div class='panel'><h3>Внешние сервисы и доступы</h3>")
    if svcs:
        a("<div class='svc'>")
        for sv in svcs:
            acc = sv.get("access", "unknown")
            word = {"yes": "доступ есть", "no": "доступа нет", "unknown": "не выяснено"}[acc]
            a("<span class='n'>%s<span class='need'>%s</span></span><span class='pill %s'>%s</span>"
              % (e(sv["name"]), e(sv.get("need", "")), acc, word))
            if sv.get("how"):
                a("<span class='how'>%s</span>" % e(sv["how"]))
        a("</div>")
    else:
        a("<div class='empty'>пока ни одного: появится, если данные откуда-то берутся</div>")
    a("</div><div class='panel'><h3>Готово, когда</h3>")
    dw = data.get("done_when", [])
    a("<ul>%s</ul>" % "".join("<li>%s</li>" % e(x) for x in dw) if dw else "<div class='empty'>ещё не договорились</div>")
    al, fb = data.get("allowed", []), data.get("forbidden", [])
    a("<div class='shelves'><div><h3 class='ok'>Можно без вопросов</h3>%s</div><div><h3 class='no'>Нельзя</h3>%s</div></div>"
      % ("<ul>%s</ul>" % "".join("<li>%s</li>" % e(x) for x in al) if al else "<div class='empty'>пусто</div>",
         "<ul>%s</ul>" % "".join("<li>%s</li>" % e(x) for x in fb) if fb else "<div class='empty'>пусто</div>"))
    a("</div></div>")
    # журнал
    log = data.get("log", [])[-6:]
    if log:
        a("<div class='panel log'>")
        for r in log:
            cls = "q" if r.get("who") == "человек" else ""
            a("<span class='t'>%s</span><span class='%s'>%s</span>" % (e(r.get("t", "")), cls, e(r.get("text", ""))))
        a("</div>")
    a("<footer>карта.json рядом с этим файлом · страница обновляется сама</footer>")
    a("</div></body></html>")
    return "\n".join(out)


def main():
    p = argparse.ArgumentParser(description="Живая карта работы архитектора: карта.json → карта.html")
    p.add_argument("folder", help="папка, где лежит карта.json")
    p.add_argument("--open", action="store_true", help="открыть карта.html в браузере")
    p.add_argument("--title", help="переопределить заголовок")
    p.add_argument("--example", action="store_true", help="создать образец карта.json, если его нет")
    args = p.parse_args()

    folder = os.path.abspath(args.folder)
    src = os.path.join(folder, "карта.json")
    dst = os.path.join(folder, "карта.html")
    if args.example and not os.path.exists(src):
        os.makedirs(folder, exist_ok=True)
        with open(src, "w", encoding="utf-8") as f:
            json.dump(EXAMPLE, f, ensure_ascii=False, indent=2)
        print("создан образец " + src)
    if not os.path.exists(src):
        fail("нет файла " + src + " (добавь --example, чтобы создать образец)", 2)
    try:
        with open(src, encoding="utf-8") as f:
            data = json.load(f)
    except ValueError as err:
        fail("карта.json не читается как JSON: %s" % err)
    check(data)
    tmp = dst + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(render(data, args.title))
    os.replace(tmp, dst)  # атомарно: браузер не поймает полуфайл
    print(dst)
    if args.open:
        cmd = ["open", dst] if sys.platform == "darwin" else ["xdg-open", dst]
        try:
            subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError as err:
            print("render_map: браузер не открылся (%s), карта лежит в %s" % (err, dst), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
