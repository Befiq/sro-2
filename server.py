# БЭКЕНД трекера привычек (Python, только стандартная библиотека).
# Хранит данные, проверяет ввод, считает серии и статистику, отдаёт всё фронтенду (index.html) в виде JSON.
# Запуск:  python server.py        -> откроется http://localhost:8000
#          python server.py test   -> тесты
import json, os, sys, calendar, webbrowser
from datetime import date, datetime, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs

HERE = os.path.dirname(os.path.abspath(__file__))
FILE = os.path.join(HERE, "data.json")
MONTHS = ["Январь", "Февраль", "Март", "Апрель", "Май", "Июнь", "Июль",
          "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"]


# ---------- хранение: {"habits": [{name, start, weekdays, time, days}], "reminders": [{text, date, time, done}]} ----------
def load():
    if os.path.exists(FILE):
        with open(FILE, encoding="utf-8") as f:
            return json.load(f)
    return {"habits": [], "reminders": []}


def save(data):
    with open(FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ---------- логика и проверка ввода (функции возвращают текст ошибки или "") ----------
def valid_time(t):
    try:
        datetime.strptime(t, "%H:%M")
        return len(t) == 5
    except ValueError:
        return False


def planned_days(h, today):
    d, result = date.fromisoformat(h["start"]), []
    while d.isoformat() <= today:
        if d.weekday() in h["weekdays"]:
            result.append(d.isoformat())
        d += timedelta(days=1)
    return result


def streaks(h, today):
    """(текущая серия, лучшая серия) по запланированным дням."""
    plan = planned_days(h, today)
    best = run = 0
    for d in plan:
        run = run + 1 if d in h["days"] else 0
        best = max(best, run)
    cur = 0
    for d in reversed(plan):
        if d in h["days"]:
            cur += 1
        elif d != today:      # сегодня ещё можно успеть
            break
    return cur, best


def percent(h, today):
    plan = planned_days(h, today)
    done = len([d for d in plan if d in h["days"]])
    return round(done / len(plan) * 100, 1) if plan else 0


def can_mark(h, day, today):
    if day > today:
        return "Нельзя отметить будущий день."
    if day < h["start"]:
        return "Этот день раньше начала привычки."
    if date.fromisoformat(day).weekday() not in h["weekdays"]:
        return "В этот день привычка не запланирована."
    return ""


def add_habit(data, name, weekdays, time, today):
    name = str(name).strip()
    if not 2 <= len(name) <= 60:
        return "Название: от 2 до 60 символов."
    if any(h["name"].lower() == name.lower() for h in data["habits"]):
        return "Такая привычка уже есть."
    if not weekdays or not all(isinstance(x, int) and 0 <= x <= 6 for x in weekdays):
        return "Выбери хотя бы один день недели."
    if time and not valid_time(time):
        return "Время нужно в формате ЧЧ:ММ."
    data["habits"].append({"name": name, "start": today, "weekdays": sorted(set(weekdays)), "time": time, "days": []})
    return ""


def add_reminder(data, text, day, time, today, now):
    text = str(text).strip()
    if not 2 <= len(text) <= 80:
        return "Текст напоминания: от 2 до 80 символов."
    try:
        date.fromisoformat(day)
    except ValueError:
        return "Укажи дату напоминания."
    if not valid_time(time):
        return "Укажи время напоминания (например, 17:00)."
    if day < today or (day == today and time < now):
        return "Это время уже прошло."
    data["reminders"].append({"text": text, "date": day, "time": time, "done": False})
    return ""


def mark(h, day, today, only_set=False):
    """Ставит отметку, а если она уже есть - снимает (кроме only_set: кнопка «сегодня»)."""
    if day in h["days"]:
        if only_set:
            return "На сегодня отметка уже есть."
        h["days"].remove(day)
        return ""
    error = can_mark(h, day, today)
    if not error:
        h["days"].append(day)
    return error


# ---------- то, что бэкенд отдаёт фронтенду ----------
def build_state(data, y, m):
    today, now = date.today().isoformat(), datetime.now().strftime("%H:%M")
    due = []     # что сегодня ещё ждёт выполнения (для оповещений)
    habits = []
    for i, h in enumerate(data["habits"]):
        cur, best = streaks(h, today)
        cells = []
        for n in range(1, calendar.monthrange(y, m)[1] + 1):
            day = date(y, m, n).isoformat()
            if day in h["days"]:
                state = "done"
            elif can_mark(h, day, today):
                state = "off"
            else:
                state = "miss" if day < today else "free"
            cells.append({"n": n, "day": day, "state": state, "today": day == today})
        if h["time"] and date.today().weekday() in h["weekdays"] and today not in h["days"]:
            due.append({"t": h["time"], "text": h["name"]})
        habits.append({"i": i, "name": h["name"], "weekdays": h["weekdays"], "time": h["time"],
                       "total": len(h["days"]), "current": cur, "best": best, "percent": percent(h, today),
                       "offset": date(y, m, 1).weekday(), "cells": cells})
    reminders = []
    for i, r in sorted(enumerate(data["reminders"]), key=lambda p: (p[1]["date"], p[1]["time"])):
        if r["date"] == today and not r["done"]:
            due.append({"t": r["time"], "text": r["text"]})
        reminders.append({"i": i, **r})
    prev_m = f"{y - 1}-12" if m == 1 else f"{y}-{m - 1:02d}"
    next_m = f"{y + 1}-01" if m == 12 else f"{y}-{m + 1:02d}"
    return {"today": today, "month": f"{y}-{m:02d}", "title": f"{MONTHS[m - 1]} {y}", "prev": prev_m,
            "next": next_m, "habits": habits, "reminders": reminders, "due": due}


def handle_action(data, action, body):
    """Выполняет действие фронтенда. Возвращает текст ошибки или ''."""
    today, now = date.today().isoformat(), datetime.now().strftime("%H:%M")
    try:
        if action == "habit":
            return add_habit(data, body.get("name", ""), body.get("weekdays", []), body.get("time", ""), today)
        if action == "reminder":
            return add_reminder(data, body.get("text", ""), body.get("date", ""), body.get("time", ""), today, now)
        if action == "mark":
            day = date.fromisoformat(body.get("day", "")).isoformat()
            return mark(data["habits"][int(body["i"])], day, today, only_set=bool(body.get("only_set")))
        if action == "reminder_done":
            r = data["reminders"][int(body["i"])]
            r["done"] = not r["done"]
            return ""
        if action == "delete":
            data["habits" if body.get("kind") == "habit" else "reminders"].pop(int(body["i"]))
            return ""
    except (ValueError, KeyError, IndexError, TypeError):
        return "Некорректные данные."
    return "Неизвестное действие."


# ---------- веб-сервер: отдаёт страницу и API ----------
class Handler(BaseHTTPRequestHandler):
    def send(self, code, body, ctype):
        self.send_response(code)
        self.send_header("Content-Type", ctype + "; charset=utf-8")
        self.end_headers()
        self.wfile.write(body if isinstance(body, bytes) else body.encode("utf-8"))

    def do_GET(self):
        url = urlparse(self.path)
        if url.path == "/":                                   # фронтенд
            with open(os.path.join(HERE, "index.html"), "rb") as f:
                self.send(200, f.read(), "text/html")
        elif url.path == "/api/state":                        # данные для фронтенда
            try:
                y, m = map(int, parse_qs(url.query).get("m", [date.today().strftime("%Y-%m")])[0].split("-"))
                date(y, m, 1)
            except ValueError:
                y, m = date.today().year, date.today().month
            self.send(200, json.dumps(build_state(load(), y, m), ensure_ascii=False), "application/json")
        else:
            self.send(404, "Не найдено", "text/plain")

    def do_POST(self):                                        # действия: /api/habit, /api/mark ...
        try:
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or "{}")
        except ValueError:
            body = {}
        data = load()
        error = handle_action(data, self.path.replace("/api/", "", 1), body if isinstance(body, dict) else {})
        if not error:
            save(data)
        self.send(200, json.dumps({"ok": not error, "error": error}, ensure_ascii=False), "application/json")

    def log_message(self, *args):
        pass


# ---------- тесты ----------
def test():
    T = "2026-10-21"      # среда
    h = {"name": "Т", "start": "2026-10-01", "weekdays": [0, 1, 2, 3, 4, 5, 6], "time": "", "days": []}
    assert streaks(h, T) == (0, 0)
    h["days"] = ["2026-10-19", "2026-10-20", "2026-10-21"]
    assert streaks(h, T) == (3, 3)                       # серия с сегодняшним днём
    h["days"] = ["2026-10-18", "2026-10-19", "2026-10-20"]
    assert streaks(h, T)[0] == 3                         # сегодня ещё не отмечено - серия жива
    h["days"] = ["2026-10-02", "2026-10-03", "2026-10-04", "2026-10-05", "2026-10-19"]
    assert streaks(h, T) == (0, 4)                       # серия прервана, рекорд 4
    h["days"] = ["2026-10-01", "2026-10-02", "2026-10-03", "2026-10-04", "2026-10-05"]
    assert percent(h, T) == 23.8                         # 5 из 21 дня
    m = {"name": "М", "start": "2026-10-01", "weekdays": [0, 2, 4], "time": "17:00",
         "days": ["2026-10-16", "2026-10-19", "2026-10-21"]}
    assert streaks(m, T)[0] == 3                         # только Пн/Ср/Пт
    assert can_mark(m, "2026-10-20", T) != ""            # вторник не запланирован
    assert can_mark(m, "2026-10-25", T) != "" and can_mark(m, "2026-09-30", T) != ""
    assert mark(m, "2026-10-21", T, only_set=True) != "" and mark(m, "2026-10-21", T) == ""   # кнопка «сегодня» не снимает
    assert valid_time("17:00") and not valid_time("7:00") and not valid_time("25:00")
    d = {"habits": [], "reminders": []}
    assert add_habit(d, "Бег", [1], "", T) == ""
    assert add_habit(d, "бег", [1], "", T) != ""         # дубликат
    assert add_habit(d, "Х", [1], "", T) != ""           # короткое название
    assert add_habit(d, "Плавание", [], "", T) != ""     # нет дней
    assert add_habit(d, "Плавание", [9], "", T) != ""    # неверный день недели
    assert add_reminder(d, "Звонок", "2026-10-21", "17:00", T, "13:00") == ""
    assert add_reminder(d, "Звонок", "2026-10-21", "12:00", T, "13:00") != ""   # время прошло
    assert add_reminder(d, "Звонок", "2026-10-20", "17:00", T, "13:00") != ""   # дата прошла
    assert add_reminder(d, "Звонок", "2026-02-30", "17:00", T, "13:00") != ""   # неверная дата
    assert handle_action(d, "mark", {"i": 5, "day": T}) != ""                   # такой привычки нет
    assert build_state(d, 2026, 10)["habits"][0]["name"] == "Бег"
    print("Все тесты пройдены.")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "test":
        test()
    else:
        print("Сервер запущен: http://localhost:8000  (остановить: Ctrl+C)")
        webbrowser.open("http://localhost:8000")
        HTTPServer(("127.0.0.1", 8000), Handler).serve_forever()
