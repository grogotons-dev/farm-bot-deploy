import logging
import sqlite3
import os
import random
from datetime import datetime, timedelta
from telegram import Update, LabeledPrice, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, PreCheckoutQueryHandler, MessageHandler, filters

# Токен будет из переменных окружения
BOT_TOKEN = os.environ.get('BOT_TOKEN')

# НАСТРОЙКИ ЭКОНОМИКИ И АДМИНА
ADMIN_ID = 7700365122
ADMIN_USERNAME = "@solotars"

# НАСТРОЙКИ TELEGRAM STARS
MIN_DEPOSIT = 10
MAX_DEPOSIT = 10000
STARS_TO_GOLD_RATE = 1
MIN_FIRST_DEPOSIT = 20

# ЖИВОТНЫЕ И ИХ ХАРАКТЕРИСТИКИ
ANIMALS = {
    "chicken": {"name": "🐔 Курочка", "price": 10, "income": 100, "emoji": "🐔", "efficiency": 10.0},
    "goose": {"name": "🦆 Гусь", "price": 50, "income": 600, "emoji": "🦆", "efficiency": 12.0},
    "turkey": {"name": "🦃 Индюк", "price": 200, "income": 2500, "emoji": "🦃", "efficiency": 12.5},
    "duck": {"name": "🦆 Утка", "price": 30, "income": 350, "emoji": "🦆", "efficiency": 11.7},
    "quail": {"name": "🥚 Перепел", "price": 5, "income": 45, "emoji": "🥚", "efficiency": 9.0},
}

# ЗАДАНИЯ
QUESTS = [
    {"id": 1, "name": "🐔 Первая ферма", "task": "Купить 1 курочку", "target": 1, "reward": 5, "type": "buy_chicken"},
    {"id": 2, "name": "💰 Первый доход", "task": "Собрать 100 яиц", "target": 100, "reward": 10, "type": "collect_eggs"},
    {"id": 3, "name": "🏆 Фермер", "task": "Купить 5 курочек", "target": 5, "reward": 25, "type": "buy_chicken"},
    {"id": 4, "name": "🎯 Сборщик", "task": "Собрать 1000 яиц", "target": 1000, "reward": 50, "type": "collect_eggs"},
    {"id": 5, "name": "💫 Инвестор", "task": "Пополнить баланс", "target": 1, "reward": 20, "type": "deposit"},
    {"id": 6, "name": "👥 Приглашатель", "task": "Пригласить 1 друга", "target": 1, "reward": 15, "type": "referral"},
    {"id": 7, "name": "🐓 Птицевод", "task": "Иметь 10 животных", "target": 10, "reward": 100, "type": "total_animals"},
    {"id": 8, "name": "💎 Богач", "task": "Накопить 500 золота", "target": 500, "reward": 75, "type": "total_gold"},
]

# РЕФЕРАЛЬНАЯ СИСТЕМА
REFERRAL_BONUS = 10
REFERRAL_BONUS_FOR_NEW = 5

# ЕЖЕДНЕВНЫЙ БОНУС
DAILY_BONUS_MIN = 1
DAILY_BONUS_MAX = 5

# ОБМЕН ЯИЦ
EXCHANGE_RATE = 500
EXCHANGE_GOLD = 5
EXCHANGE_STARS = 5

# БАЗА ДАННЫХ
def init_database():
    conn = sqlite3.connect('farm_bot.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            chickens INTEGER DEFAULT 0,
            geese INTEGER DEFAULT 0,
            turkeys INTEGER DEFAULT 0,
            ducks INTEGER DEFAULT 0,
            quails INTEGER DEFAULT 0,
            eggs INTEGER DEFAULT 0,
            gold INTEGER DEFAULT 10,
            stars INTEGER DEFAULT 0,
            last_collect TEXT,
            last_daily_bonus TEXT,
            total_deposited INTEGER DEFAULT 0,
            total_withdrawn INTEGER DEFAULT 0,
            has_first_deposit INTEGER DEFAULT 0,
            referred_by INTEGER DEFAULT 0,
            referrals_count INTEGER DEFAULT 0,
            completed_quests TEXT DEFAULT '',
            got_first_daily_bonus INTEGER DEFAULT 0
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            amount INTEGER,
            type TEXT,
            status TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

def get_user(user_id):
    conn = sqlite3.connect('farm_bot.db')
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
    user = cursor.fetchone()
    conn.close()
    if user:
        return {
            'user_id': user[0], 'username': user[1],
            'chickens': user[2], 'geese': user[3], 'turkeys': user[4],
            'ducks': user[5], 'quails': user[6], 'eggs': user[7],
            'gold': user[8], 'stars': user[9], 'last_collect': user[10],
            'last_daily_bonus': user[11], 'total_deposited': user[12],
            'total_withdrawn': user[13], 'has_first_deposit': user[14],
            'referred_by': user[15], 'referrals_count': user[16],
            'completed_quests': user[17] or '', 'got_first_daily_bonus': user[18]
        }
    return None

def update_user(user_id, username, **kwargs):
    conn = sqlite3.connect('farm_bot.db')
    cursor = conn.cursor()
    user = get_user(user_id)
    if user:
        updates = []
        params = []
        for key, value in kwargs.items():
            if value is not None:
                updates.append(f"{key} = ?")
                params.append(value)
        if username:
            updates.append("username = ?")
            params.append(username)
        if updates:
            query = f"UPDATE users SET {', '.join(updates)} WHERE user_id = ?"
            params.append(user_id)
            cursor.execute(query, params)
    else:
        fields = ['user_id', 'username']
        values = [user_id, username]
        placeholders = ['?', '?']
        for key, value in kwargs.items():
            if value is not None:
                fields.append(key)
                values.append(value)
                placeholders.append('?')
        query = f"INSERT INTO users ({', '.join(fields)}) VALUES ({', '.join(placeholders)})"
        cursor.execute(query, values)
    conn.commit()
    conn.close()

def add_transaction(user_id, amount, transaction_type, status="completed"):
    conn = sqlite3.connect('farm_bot.db')
    cursor = conn.cursor()
    cursor.execute(
        'INSERT INTO transactions (user_id, amount, type, status) VALUES (?, ?, ?, ?)',
        (user_id, amount, transaction_type, status)
    )
    conn.commit()
    conn.close()

def get_total_animals(user):
    return user['chickens'] + user['geese'] + user['turkeys'] + user['ducks'] + user['quails']

def get_total_income(user):
    return (user['chickens'] * ANIMALS['chicken']['income'] +
            user['geese'] * ANIMALS['goose']['income'] +
            user['turkeys'] * ANIMALS['turkey']['income'] +
            user['ducks'] * ANIMALS['duck']['income'] +
            user['quails'] * ANIMALS['quail']['income'])

def create_exchange_progress_bar(current_eggs, target_eggs):
    percentage = min(100, int((current_eggs / target_eggs) * 100))
    filled_blocks = int(percentage / 10)
    empty_blocks = 10 - filled_blocks
    progress_bar = "🟩" * filled_blocks + "⬜" * empty_blocks
    return f"{progress_bar} {percentage}% ({current_eggs}/{target_eggs})"

# КОМАНДА START
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    username = update.effective_user.first_name
    
    referred_by = None
    if context.args and context.args[0].startswith('ref_'):
        try:
            referred_by = int(context.args[0][4:])
            if referred_by == user_id or not get_user(referred_by):
                referred_by = None
        except:
            referred_by = None
    
    user = get_user(user_id)
    if not user:
        update_data = {
            'gold': 10 + (REFERRAL_BONUS_FOR_NEW if referred_by else 0),
            'referred_by': referred_by
        }
        update_user(user_id, username, **update_data)
        
        welcome_text = (
            f"🐔 Добро пожаловать на ферму, {username}!\n\n"
            f"🎁 Ваш начальный бонус: {10 + (REFERRAL_BONUS_FOR_NEW if referred_by else 0)} золота 💰\n"
        )
        
        if referred_by:
            welcome_text += f"💫 Вы зарегистрировались по ссылке друга!\n"
            welcome_text += f"💰 Бонус за регистрацию: {REFERRAL_BONUS_FOR_NEW} золота\n\n"
        
        welcome_text += (
            "💰 Экономика фермы:\n"
            f"🐔 1 курица = {ANIMALS['chicken']['price']} золота\n"
            f"🥚 1 курица = {ANIMALS['chicken']['income']} яиц/день\n"
            f"💎 {EXCHANGE_RATE} яиц = {EXCHANGE_GOLD} золота + {EXCHANGE_STARS} звезд\n\n"
            f"💫 Пополнение через Telegram Stars\n"
            f"⭐ 1 звезда = {STARS_TO_GOLD_RATE} золото\n"
            f"🔐 Вывод доступен после пополнения от {MIN_FIRST_DEPOSIT} звезд\n\n"
            "💡 Получите первый ежедневный бонус чтобы активировать реферальную систему!\n\n"
            "Нажмите /menu чтобы начать!"
        )
        
        await update.message.reply_text(welcome_text)
    else:
        progress_bar = create_exchange_progress_bar(user['eggs'], EXCHANGE_RATE)
        
        await update.message.reply_text(
            f"С возвращением на ферму, {username}! 🐔\n\n"
            f"📊 Ваши активы:\n"
            f"🐔 Животных: {get_total_animals(user)}\n"
            f"🥚 Яиц: {user['eggs']}\n" 
            f"💰 Золота: {user['gold']}\n"
            f"⭐ Звезд: {user['stars']}\n\n"
            f"📈 Прогресс до обмена:\n{progress_bar}\n\n"
            "Нажмите /menu"
        )

# КОМАНДА MENU
async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🐔 Купить животных", callback_data="buy_animals")],
        [InlineKeyboardButton("🥚 Собрать яйца", callback_data="collect_eggs")],
        [InlineKeyboardButton("💎 Обменять яйца", callback_data="exchange")],
        [InlineKeyboardButton("💫 Пополнить баланс", callback_data="deposit")],
        [InlineKeyboardButton("📊 Мой баланс", callback_data="balance")],
        [InlineKeyboardButton("⭐ Вывод звезд", callback_data="withdraw")],
        [InlineKeyboardButton("🎯 Задания", callback_data="quests")],
        [InlineKeyboardButton("👥 Рефералы", callback_data="referrals")],
        [InlineKeyboardButton("🏅 Лидерборд", callback_data="leaderboard")],
        [InlineKeyboardButton("👨‍💻 Контакты", callback_data="contacts")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if update.message:
        await update.message.reply_text("🏠 Главное меню фермы:", reply_markup=reply_markup)
    else:
        await update.callback_query.edit_message_text("🏠 Главное меню фермы:", reply_markup=reply_markup)

# ОБРАБОТЧИК КНОПОК
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    username = query.from_user.first_name
    user = get_user(user_id)
    
    if query.data == "buy_animals":
        keyboard = []
        for animal_type, animal in ANIMALS.items():
            button_text = f"{animal['emoji']} {animal['name']} ({animal['price']} золота)"
            keyboard.append([InlineKeyboardButton(button_text, callback_data=f"buy_{animal_type}")])
        
        keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="back_to_menu")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        animals_info = "🐔 Магазин животных\n\n💰 Доступные животные:\n"
        for animal_type, animal in ANIMALS.items():
            animals_info += f"{animal['emoji']} {animal['name']} - {animal['price']} золота ({animal['income']} яиц/день)\n"
        
        animals_info += f"\n💎 Ваш баланс: {user['gold']} золота"
        await query.edit_message_text(animals_info, reply_markup=reply_markup)
    
    elif query.data.startswith("buy_"):
        animal_type = query.data[4:]
        animal = ANIMALS[animal_type]
        
        if user['gold'] >= animal['price']:
            new_gold = user['gold'] - animal['price']
            current_count = user[animal_type + 's']
            new_count = current_count + 1
            
            update_user(user_id, username, gold=new_gold, **{animal_type + 's': new_count})
            
            await query.edit_message_text(
                f"✅ Вы купили {animal['name'].lower()}! {animal['emoji']}\n\n"
                f"Теперь у вас: {new_count} {animal['name'].lower()}\n"
                f"Осталось золота: {new_gold}💰\n\n"
                f"💎 Доход: {animal['income']} яиц/день\n"
                f"♾️ Доход с животных - бесконечный!"
            )
        else:
            await query.edit_message_text(
                f"❌ Недостаточно золота! Нужно {animal['price']}💰\n"
                f"У вас только: {user['gold']}💰\n\n"
                "Собирайте яйца и обменивайте на золото!"
            )
    
    elif query.data == "collect_eggs":
        total_income = get_total_income(user)
        if total_income > 0:
            new_eggs = user['eggs'] + total_income
            update_user(user_id, username, eggs=new_eggs)
            
            progress_bar = create_exchange_progress_bar(new_eggs, EXCHANGE_RATE)
            
            await query.edit_message_text(
                f"🥚 Вы собрали {total_income} яиц!\n\n"
                f"📊 Теперь у вас:\n"
                f"🥚 Яиц: {new_eggs}\n"  
                f"🐔 Животных: {get_total_animals(user)}\n\n"
                f"📈 Ежедневный доход: {total_income} яиц\n\n"
                f"📊 Прогресс до обмена:\n{progress_bar}\n\n"
                f"♾️ Доход с животных - бесконечный!"
            )
        else:
            await query.edit_message_text(
                "😔 У вас нет животных!\n\n"
                "Купите хотя бы одно животное чтобы собирать яйца 🐔\n"
                "♾️ Доход с животных - бесконечный!"
            )
    
    elif query.data == "exchange":
        if user['eggs'] >= EXCHANGE_RATE:
            exchanges = user['eggs'] // EXCHANGE_RATE
            eggs_used = exchanges * EXCHANGE_RATE
            gold_earned = exchanges * EXCHANGE_GOLD
            stars_earned = exchanges * EXCHANGE_STARS
            
            new_eggs = user['eggs'] - eggs_used
            new_gold = user['gold'] + gold_earned
            new_stars = user['stars'] + stars_earned
            
            update_user(user_id, username, eggs=new_eggs, gold=new_gold, stars=new_stars)
            
            progress_bar = create_exchange_progress_bar(new_eggs, EXCHANGE_RATE)
            
            await query.edit_message_text(
                f"💎 Обменяли {eggs_used}🥚 на:\n"
                f"💰 {gold_earned} золота\n"
                f"⭐ {stars_earned} звезд\n\n"
                f"📊 Теперь у вас:\n"
                f"🥚 Яиц: {new_eggs}\n"
                f"💰 Золота: {new_gold}\n"
                f"⭐ Звезд: {new_stars}\n\n"
                f"📊 Прогресс до следующего обмена:\n{progress_bar}"
            )
        else:
            progress_bar = create_exchange_progress_bar(user['eggs'], EXCHANGE_RATE)
            await query.edit_message_text(
                f"❌ Недостаточно яиц для обмена!\n\n"
                f"Нужно: {EXCHANGE_RATE}🥚\n"
                f"У вас: {user['eggs']}🥚\n\n"
                f"📊 Прогресс до обмена:\n{progress_bar}\n\n"
                "Собирайте больше яиц или купите больше животных!"
            )
    
    elif query.data == "deposit":
        keyboard = [
            [InlineKeyboardButton("💫 25 звезд", callback_data="deposit_25")],
            [InlineKeyboardButton("💫 50 звезд", callback_data="deposit_50")],
            [InlineKeyboardButton("💫 100 звезд", callback_data="deposit_100")],
            [InlineKeyboardButton("💫 Другая сумма", callback_data="deposit_custom")],
            [InlineKeyboardButton("🔙 Назад", callback_data="back_to_menu")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            f"💫 Пополнение баланса через Telegram Stars\n\n"
            f"💰 Курс: 1⭐ = {STARS_TO_GOLD_RATE} золото\n"
            f"📊 Минимум: {MIN_DEPOSIT} звезд\n"
            f"🔐 Вывод доступен после пополнения от {MIN_FIRST_DEPOSIT} звезд\n\n"
            f"💎 Ваш баланс:\n"
            f"💰 Золота: {user['gold']}\n"
            f"⭐ Звезд: {user['stars']}",
            reply_markup=reply_markup
        )
    
    elif query.data.startswith("deposit_"):
        if query.data == "deposit_custom":
            await query.edit_message_text("💫 Введите сумму для пополнения (от 10 до 10000 звезд):")
            context.user_data['awaiting_deposit'] = True
            return
        
        amount = int(query.data.split('_')[1])
        await process_deposit(query, user_id, amount, context)
    
    elif query.data == "balance":
        total_animals = get_total_animals(user)
        total_income = get_total_income(user)
        
        progress_bar = create_exchange_progress_bar(user['eggs'], EXCHANGE_RATE)
        
        balance_text = (
            f"📊 Ваш баланс и статистика\n\n"
            f"💰 Золото: {user['gold']}\n"
            f"⭐ Звезды: {user['stars']}\n"
            f"🥚 Яйца: {user['eggs']}\n\n"
            f"🐔 Животные:\n"
            f"🐔 Курочек: {user['chickens']}\n"
            f"🦆 Гусей: {user['geese']}\n"
            f"🦃 Индюков: {user['turkeys']}\n"
            f"🦆 Уток: {user['ducks']}\n"
            f"🥚 Перепелов: {user['quails']}\n\n"
            f"📈 Всего животных: {total_animals}\n"
            f"💎 Ежедневный доход: {total_income} яиц\n\n"
            f"📊 Прогресс до обмена:\n{progress_bar}\n\n"
            f"👥 Приглашено друзей: {user['referrals_count']}"
        )
        
        await query.edit_message_text(balance_text)
    
    elif query.data == "withdraw":
        if not user['has_first_deposit']:
            await query.edit_message_text(
                f"❌ Вывод пока недоступен!\n\n"
                f"🔐 Для доступа к выводу необходимо:\n"
                f"💫 Пополнить баланс от {MIN_FIRST_DEPOSIT} звезд\n\n"
                f"💰 После этого вы сможете выводить заработанные звезды!"
            )
            return
        
        if user['stars'] < 10:
            await query.edit_message_text(
                f"❌ Недостаточно звезд для вывода!\n\n"
                f"💰 Минимальная сумма вывода: 10 звезд\n"
                f"💫 У вас: {user['stars']} звезд\n\n"
                f"💡 Продолжайте собирать яйца и обменивать их!"
            )
            return
        
        keyboard = [
            [InlineKeyboardButton("⭐ Вывести 10 звезд", callback_data="withdraw_10")],
            [InlineKeyboardButton("⭐ Вывести все звезды", callback_data="withdraw_all")],
            [InlineKeyboardButton("🔙 Назад", callback_data="back_to_menu")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            f"⭐ Вывод звезд\n\n"
            f"💰 Доступно для вывода: {user['stars']} звезд\n"
            f"💸 Минимальная сумма: 10 звезд\n\n"
            f"💡 После запроса администратор свяжется с вами\n"
            f"👨‍💻 Контакты администратора: {ADMIN_USERNAME}",
            reply_markup=reply_markup
        )
    
    elif query.data.startswith("withdraw_"):
        if query.data == "withdraw_all":
            amount = user['stars']
        else:
            amount = int(query.data.split('_')[1])
        
        if user['stars'] < amount:
            await query.edit_message_text("❌ Недостаточно звезд для вывода!")
            return
        
        new_stars = user['stars'] - amount
        new_withdrawn = user['total_withdrawn'] + amount
        update_user(user_id, username, stars=new_stars, total_withdrawn=new_withdrawn)
        
        add_transaction(user_id, amount, "withdrawal", "pending")
        
        await query.edit_message_text(
            f"✅ Запрос на вывод отправлен!\n\n"
            f"💫 Сумма: {amount} звезд\n"
            f"💰 Осталось звезд: {new_stars}\n\n"
            f"👨‍💻 Администратор свяжется с вами: {ADMIN_USERNAME}\n"
            f"⏱️ Обычно обработка занимает до 24 часов"
        )
    
    elif query.data == "quests":
        completed_quests = user['completed_quests'].split(',') if user['completed_quests'] else []
        quests_text = "🎯 Доступные задания\n\n"
        
        for quest in QUESTS:
            status = "✅ Выполнено" if str(quest['id']) in completed_quests else "❌ Не выполнено"
            quests_text += f"{quest['name']}\n{quest['task']}\nНаграда: {quest['reward']} золота\nСтатус: {status}\n\n"
        
        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="back_to_menu")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(quests_text, reply_markup=reply_markup)
    
    elif query.data == "referrals":
        ref_link = f"https://t.me/{(await context.bot.get_me()).username}?start=ref_{user_id}"
        
        referrals_text = (
            f"👥 Реферальная система\n\n"
            f"💫 Приглашайте друзей и получайте бонусы!\n\n"
            f"💰 За каждого приглашенного друга:\n"
            f"🎁 Вы получаете: {REFERRAL_BONUS} золота\n"
            f"🎁 Друг получает: {REFERRAL_BONUS_FOR_NEW} золота\n\n"
            f"🔗 Ваша реферальная ссылка:\n`{ref_link}`\n\n"
            f"📊 Статистика:\n"
            f"👥 Приглашено друзей: {user['referrals_count']}\n"
            f"💎 Заработано золота: {user['referrals_count'] * REFERRAL_BONUS}"
        )
        
        keyboard = [
            [InlineKeyboardButton("🔗 Поделиться ссылкой", url=f"https://t.me/share/url?url={ref_link}&text=Присоединяйся%20к%20моей%20ферме%20в%20Telegram!")],
            [InlineKeyboardButton("🔙 Назад", callback_data="back_to_menu")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(referrals_text, reply_markup=reply_markup)
    
    elif query.data == "leaderboard":
        keyboard = [
            [InlineKeyboardButton("🐔 По животным", callback_data="leaderboard_animals")],
            [InlineKeyboardButton("👥 По рефералам", callback_data="leaderboard_referrals")],
            [InlineKeyboardButton("🔙 Назад", callback_data="back_to_menu")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text("🏅 Лидерборд\n\nВыберите категорию:", reply_markup=reply_markup)
    
    elif query.data == "contacts":
        contacts_text = (
            f"👨‍💻 Контакты\n\n"
            f"💫 По вопросам пополнения и вывода:\n{ADMIN_USERNAME}\n\n"
            f"🐛 Сообщить об ошибке:\n{ADMIN_USERNAME}\n\n"
            f"💡 Предложения по улучшению:\n{ADMIN_USERNAME}\n\n"
            f"⏱️ Время ответа: до 24 часов"
        )
        
        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="back_to_menu")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(contacts_text, reply_markup=reply_markup)
    
    elif query.data == "back_to_menu":
        await menu(update, context)

# ОБРАБОТКА ДЕПОЗИТА
async def process_deposit(query, user_id, amount, context, message=None):
    prices = [LabeledPrice(f"Пополнение на {amount} звезд", amount * 100)]
    
    try:
        await context.bot.send_invoice(
            chat_id=user_id,
            title="💫 Пополнение баланса",
            description=f"Пополнение на {amount} звезд в игре Ферма",
            payload=f"deposit_{amount}_{user_id}",
            provider_token="",
            currency="XTR",
            prices=prices,
            need_email=False,
            need_phone_number=False,
            need_shipping_address=False,
        )
    except Exception as e:
        error_msg = f"❌ Ошибка при создании счета: {str(e)}"
        await query.edit_message_text(error_msg)

# PRE CHECKOUT
async def precheckout_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.pre_checkout_query
    await query.answer(ok=True)

# УСПЕШНЫЙ ПЛАТЕЖ
async def successful_payment_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    username = update.effective_user.first_name
    payment = update.message.successful_payment
    
    amount = payment.total_amount // 100
    gold_earned = amount * STARS_TO_GOLD_RATE
    
    user = get_user(user_id)
    new_gold = user['gold'] + gold_earned
    new_stars = user['stars'] + amount
    new_deposited = user['total_deposited'] + amount
    
    has_first_deposit = 1 if amount >= MIN_FIRST_DEPOSIT else user['has_first_deposit']
    
    update_user(
        user_id, 
        username, 
        gold=new_gold, 
        stars=new_stars, 
        total_deposited=new_deposited,
        has_first_deposit=has_first_deposit
    )
    
    add_transaction(user_id, amount, "deposit", "completed")
    
    deposit_status = "✅ Теперь доступен вывод!" if amount >= MIN_FIRST_DEPOSIT and not user['has_first_deposit'] else ""
    
    await update.message.reply_text(
        f"✅ Оплата прошла успешно!\n\n"
        f"💫 Пополнено: {amount} звезд\n"
        f"💰 Получено: {gold_earned} золота\n\n"
        f"📊 Теперь у вас:\n"
        f"💰 Золота: {new_gold}\n"
        f"⭐ Звезд: {new_stars}\n\n"
        f"{deposit_status}"
    )

# ОБРАБОТКА СООБЩЕНИЙ
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message and context.user_data.get('awaiting_deposit'):
        try:
            amount = int(update.message.text)
            if amount < MIN_DEPOSIT or amount > MAX_DEPOSIT:
                await update.message.reply_text(f"❌ Сумма должна быть от {MIN_DEPOSIT} до {MAX_DEPOSIT} звезд!")
                return
            
            user_id = update.effective_user.id
            await process_deposit(None, user_id, amount, context, update.message)
            context.user_data['awaiting_deposit'] = False
            
        except ValueError:
            await update.message.reply_text("❌ Пожалуйста, введите число!")

# ЗАПУСК БОТА
def main():
    init_database()
    application = Application.builder().token(BOT_TOKEN).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("menu", menu))
    application.add_handler(PreCheckoutQueryHandler(precheckout_handler))
    application.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment_handler))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    print("🚀 Бот запущен!")
    application.run_polling()

if __name__ == "__main__":
    main()
