import asyncio
import json
import os
import random
import time
from gtts import gTTS
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.types import FSInputFile
from aiogram.utils.keyboard import InlineKeyboardBuilder
from apscheduler.schedulers.asyncio import AsyncIOScheduler

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
QUESTIONS_FILE = "questions.json"

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
scheduler = AsyncIOScheduler()

user_intervals = {}
QUESTIONS = []

# Хранилище временного выбора пользователя при множественном ответе
# Формат: { (chat_id, question_id): set(выбранные_индексы) }
user_selections = {}


def generate_audio(text: str, filename: str) -> str:
    tts = gTTS(text=text, lang="de")
    tts.save(filename)
    return filename


# Буквенные обозначения для вариантов ответа
LETTERS = ["A", "B", "C", "D", "E", "F"]


def build_quiz_keyboard(q_id: int, options_count: int, selected_indices: set):
    """Создает компактные кнопки вида [ ] A, [x] B."""
    builder = InlineKeyboardBuilder()

    for idx in range(options_count):
        letter = LETTERS[idx] if idx < len(LETTERS) else str(idx + 1)
        checkbox = "[x]" if idx in selected_indices else "[ ]"
        builder.button(text=f"{checkbox} {letter}", callback_data=f"toggle_{q_id}_{idx}")

    # Размещаем варианты по 2 кнопки в ряд
    builder.adjust(2)

    # Кнопку подтверждения ставим на отдельную строчку снизу
    builder.row(types.InlineKeyboardButton(text="📥 Подтвердить ответ", callback_data=f"submit_{q_id}"))
    return builder.as_markup()


async def send_quiz_to_user(user_id: int):
    if not QUESTIONS:
        return

    q = random.choice(QUESTIONS)
    q_id = q['id']

    user_selections[(user_id, q_id)] = set()

    # Формируем список вариантов ответа прямо в тексте
    options_text = ""
    for idx, opt in enumerate(q['options']):
        letter = LETTERS[idx] if idx < len(LETTERS) else str(idx + 1)
        options_text += f"**{letter})** {opt}\n"

    question_text = (
        f"❓ **Вопрос №{q_id}:**\n\n"
        f"{q['question']}\n\n"
        f"**Варианты ответов:**\n"
        f"{options_text}\n"
        f"⚠️ *Отметьте варианты на кнопках ниже и нажмите 'Подтвердить'.*"
    )

    audio_path = f"q_{q_id}_{int(time.time())}.mp3"

    try:
        # 1. Отправляем голосовое сообщение с озвучкой вопроса
        generate_audio(q['question'], audio_path)
        voice_file = FSInputFile(audio_path)
        await bot.send_voice(chat_id=user_id, voice=voice_file)

        # 2. Если у вопроса есть картинка — отправляем её
        if q.get("image"):
            try:
                # Если image — это URL-ссылка
                if q["image"].startswith("http://") or q["image"].startswith("https://"):
                    await bot.send_photo(chat_id=user_id, photo=q["image"])
                # Если image — это локальный файл на компьютере (например, "images/101.jpg")
                elif os.path.exists(q["image"]):
                    photo_file = FSInputFile(q["image"])
                    await bot.send_photo(chat_id=user_id, photo=photo_file)
            except Exception as img_err:
                print(f"Не удалось отправить картинку к вопросу {q_id}: {img_err}")

        # 3. Отправляем текст вопроса и кнопки с галочками
        markup = build_quiz_keyboard(q_id, len(q['options']), set())
        await bot.send_message(
            chat_id=user_id,
            text=question_text,
            reply_markup=markup,
            parse_mode="Markdown"
        )
    except Exception as e:
        print(f"Ошибка при отправке пользователю {user_id}: {e}")
    finally:
        if os.path.exists(audio_path):
            os.remove(audio_path)



def schedule_user_job(user_id: int, minutes: int):
    job_id = f"job_{user_id}"
    if scheduler.get_job(job_id):
        scheduler.remove_job(job_id)

    scheduler.add_job(
        send_quiz_to_user,
        "interval",
        minutes=minutes,
        args=[user_id],
        id=job_id
    )


# ----------------------------------------------------------------------
# ОБРАБОТКА НАЖАТИЙ НА КНОПКИ
# ----------------------------------------------------------------------

# 1. Переключение галочки (выбрал / снял выбор)
@dp.callback_query(F.data.startswith("toggle_"))
async def handle_toggle(callback: types.CallbackQuery):
    _, q_id_str, opt_idx_str = callback.data.split("_")
    q_id, opt_idx = int(q_id_str), int(opt_idx_str)
    user_id = callback.message.chat.id

    q = next((item for item in QUESTIONS if item["id"] == q_id), None)
    if not q:
        await callback.answer("Вопрос устарел.")
        return

    key = (user_id, q_id)
    if key not in user_selections:
        user_selections[key] = set()

    # Переключаем состояние галочки
    if opt_idx in user_selections[key]:
        user_selections[key].remove(opt_idx)
    else:
        user_selections[key].add(opt_idx)

    # Обновляем клавиатуру у сообщения
    markup = build_quiz_keyboard(q_id, len(q['options']), user_selections[key])
    await callback.message.edit_reply_markup(reply_markup=markup)
    await callback.answer()


# 2. Нажатие на «Подтвердить ответ»
@dp.callback_query(F.data.startswith("submit_"))
async def handle_submit(callback: types.CallbackQuery):
    q_id = int(callback.data.split("_")[1])
    user_id = callback.message.chat.id
    key = (user_id, q_id)

    q = next((item for item in QUESTIONS if item["id"] == q_id), None)
    if not q:
        await callback.answer("Вопрос не найден.")
        return

    selected = user_selections.get(key, set())

    # Приводим правильные ответы из JSON к множеству (set)
    correct_set = set(q["correct"]) if isinstance(q["correct"], list) else {q["correct"]}

    # Ответ считается правильным, только если полностью совпали ВСЕ выбранные галочки
    is_correct = (selected == correct_set)

    # Формируем список верных вариантов для текста ответа
    correct_options_text = "\n".join([f"• {q['options'][idx]}" for idx in correct_set])

    if is_correct:
        text = f"✅ **Правильно!**\n\n💡 {q['explanation']}"
    else:
        text = (
            f"❌ **Неправильно.**\n\n"
            f"**Правильные варианты:**\n{correct_options_text}\n\n"
            f"💡 {q['explanation']}"
        )

    # Очищаем временный выбор из памяти
    user_selections.pop(key, None)

    await callback.message.edit_text(text, parse_mode="Markdown")
    await callback.answer()


# ----------------------------------------------------------------------
# КОМАНДЫ И ЗАПУСК
# ----------------------------------------------------------------------

@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    user_id = message.chat.id
    default_interval = 30
    user_intervals[user_id] = default_interval
    schedule_user_job(user_id, default_interval)

    await message.answer(
        f"👋 Бот запущен! Вопросы отправляются каждые **{default_interval} минут**.\n\n"
        f"• `/settime <мин>` — изменить интервал\n"
        f"• `/stop` — остановить",
        parse_mode="Markdown"
    )
    await send_quiz_to_user(user_id)


@dp.message(Command("settime"))
async def set_time_cmd(message: types.Message):
    user_id = message.chat.id
    args = message.text.split(maxsplit=1)

    if len(args) < 2 or not args[1].isdigit():
        await message.answer("⚠️ Укажите число минут. Пример: `/settime 15`", parse_mode="Markdown")
        return

    minutes = int(args[1])
    user_intervals[user_id] = minutes
    schedule_user_job(user_id, minutes)
    await message.answer(f"✅ Интервал изменен на **{minutes} минут**.")


@dp.message(Command("stop"))
async def stop_cmd(message: types.Message):
    user_id = message.chat.id
    job_id = f"job_{user_id}"
    if scheduler.get_job(job_id):
        scheduler.remove_job(job_id)
    await message.answer("🛑 Отправка вопросов остановлена.")


async def main():
    global QUESTIONS
    if not os.path.exists(QUESTIONS_FILE):
        print(f"❌ Файл {QUESTIONS_FILE} не найден!")
        return

    with open(QUESTIONS_FILE, "r", encoding="utf-8") as f:
        QUESTIONS = json.load(f)

    scheduler.start()
    print("🤖 Бот запущен (режим множественного выбора)!")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())