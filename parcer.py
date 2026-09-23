import json
import re
import requests
from bs4 import BeautifulSoup

OUTPUT_FILE = "questions.json"

# Базовый набор вопросов на случай отсутствия сети или блокировки
FALLBACK_QUESTIONS = [
    {
        "id": 1,
        "question": "Welche Bedeutung hat ein gelbes Blinklicht an einer Kreuzung?",
        "options": ["Erhöhte Aufmerksamkeit", "Halt vor der Kreuzung", "Vorfahrtsstraße"],
        "correct": 0,
        "explanation": "Желтый мигающий сигнал означает повышенное внимание."
    },
    {
        "id": 2,
        "question": "Wie lang ist der Reaktionsweg bei 50 km/h?",
        "options": ["10 Meter", "15 Meter", "25 Meter"],
        "correct": 1,
        "explanation": "Формула реакционного пути: (50 / 10) * 3 = 15 метров."
    },
    {
        "id": 3,
        "question": "Was gilt bei einer Einsatzfahrt mit Blaulicht und Folgetonhorn?",
        "options": ["Sofort Platz machen", "Weiterfahren wie bisher", "Stehen bleiben auf der Spur"],
        "correct": 0,
        "explanation": "Транспортным средствам с включенным проблесковым маячком и сиреной нужно незамедлительно уступить дорогу."
    }
]


def fetch_open_questions():
    print("Пробуем получить открытые вопросы...")
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    # Резервный открытый источник билетов
    url = "https://raw.githubusercontent.com/quiz-data/austria-driving-licence/main/questions_de.json"

    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Успешно скачано {len(data)} вопросов!")
            return data
    except Exception as e:
        print(f"Не удалось выкачать внешнюю базу: {e}")

    return None


def main():
    questions = fetch_open_questions()

    # Если внешняя загрузка не удалась, сохраняем стартовую локальную базу
    if not questions:
        print("Используем базовый проверенный комплект вопросов...")
        questions = FALLBACK_QUESTIONS

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(questions, f, ensure_ascii=False, indent=2)

    print(f"Готово! Файл `{OUTPUT_FILE}` успешно создан. Можно запускать бота (`bot.py`).")


if __name__ == "__main__":
    main()