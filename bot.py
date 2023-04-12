import math

from aiogram import Bot, Dispatcher, types, executor
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup

from api_requests import request
from database import orm
from settings import bot_config
from settings.api_config import conditions

bot = Bot(token=bot_config.bot_token)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)


class ChoiceCityWeather(StatesGroup):
    waiting_city = State()


class SetUserCity(StatesGroup):
    waiting_user_city = State()


class Menu:
    markup = types.reply_keyboard.ReplyKeyboardMarkup(row_width=1)

    btn1 = types.KeyboardButton('Погода в моем городе')
    btn2 = types.KeyboardButton('Погода в другом городе')
    btn3 = types.KeyboardButton('История')
    btn4 = types.KeyboardButton('Установить свой город')
    markup.add(btn1, btn2, btn3, btn4)


def get_weather_data(city, data):
    text = f'''<b>Погода в городе {city.get("waiting_city")}</b>\n
— <b>Температура</b>: {data["temp"]}°C\n
— <b>Состояние</b>: {conditions.get(data["condition"])}\n
— <b>Ощущается как</b> {data["feels_like"]}°C\n
— <b>Скорость ветра</b>: {data["wind_speed"]} м/с\n
— <b>Давление</b>: {data["pressure_mm"]} мм'''
    return text


async def check_first_char_city(message):
    if message.text[0].islower():
        await message.answer('Будьте добры писать название города\
 с заглавной буквы.')
        return
    return 1


@dp.message_handler(commands=['start'])
async def start_message(message: types.Message):
    orm.add_user(message.from_user.id)

    Menu

    text = f'Приветствую, {message.from_user.first_name}!\nЯ бот, который расскажет\
 Вам о погоде на сегодня.'
    await message.answer(text, reply_markup=Menu.markup)


@dp.message_handler(regexp='Погода в моем городе')
async def get_user_city_weather(message: types.Message):
    markup = types.reply_keyboard.ReplyKeyboardMarkup(
        row_width=1,
        resize_keyboard=True)
    btn1 = types.KeyboardButton('Меню')
    markup.add(btn1)

    city = orm.get_user_city(message.from_user.id)
    if city is None:
        text = 'Пожалуйста, установите город Вашего проживания.'
        markup = types.reply_keyboard.ReplyKeyboardMarkup(
            row_width=1,
            resize_keyboard=True)
        await message.answer(text, reply_markup=markup)
        return

    data = request.get_weather(city)
    orm.create_report(message.from_user.id, data['temp'], data['condition'],
                      data['feels_like'], data['wind_speed'],
                      data['pressure_mm'], city=city)

    city = {'waiting_city': city}
    text = get_weather_data(city, data)
    await message.answer(text, reply_markup=markup, parse_mode='HTML')


@dp.message_handler(regexp='Меню')
async def back_to_menu(message: types.Message):
    await start_message(message)


@dp.message_handler(regexp='Погода в другом городе')
async def city_start(message: types.Message):
    markup = types.reply_keyboard.ReplyKeyboardMarkup(
        row_width=1,
        resize_keyboard=True)

    btn1 = types.KeyboardButton('Меню')
    markup.add(btn1)

    text = 'Введите название города.'
    await message.answer(text, reply_markup=markup)
    await ChoiceCityWeather.waiting_city.set()


@dp.message_handler(state=ChoiceCityWeather.waiting_city)
async def city_chosen(message: types.Message, state: FSMContext):
    if await check_first_char_city(message):
        await state.update_data(waiting_city=message.text)

        Menu

        markup = types.reply_keyboard.ReplyKeyboardMarkup(row_width=1)

        city = await state.get_data()
        try:
            data = request.get_weather(city.get('waiting_city'))

            text = get_weather_data(city, data)
            await message.answer(text, reply_markup=Menu.markup, parse_mode='HTML')
            await state.finish()
        except TypeError:
            text = 'Увы, такого города нет в базе данных :('
            await message.answer(text, reply_markup=Menu.markup, parse_mode='HTML')
            await state.finish()


@dp.message_handler(regexp='Установить свой город')
async def set_user_city_start(message: types.Message):
    markup = types.reply_keyboard.ReplyKeyboardMarkup(
        row_width=1,
        resize_keyboard=True)
    btn1 = types.KeyboardButton('Меню')
    markup.add(btn1)

    text = 'В каком городе проживаете?'
    await message.answer(text, reply_markup=markup)
    await SetUserCity.waiting_user_city.set()


@dp.message_handler(state=SetUserCity.waiting_user_city)
async def user_city_chosen(message: types.Message, state: FSMContext):
    if await check_first_char_city(message):
        await state.update_data(waiting_user_city=message.text)

        user_data = await state.get_data()
        orm.set_user_city(message.from_user.id, user_data.get('waiting_user_city'))

        Menu

        text = f'Записал. Вы живете в городе {user_data.get("waiting_user_city")}.'
        await message.answer(text, reply_markup=Menu.markup)
        await state.finish()


@dp.message_handler(state=ChoiceCityWeather.waiting_city)
async def city_chosen(message: types.Message, state: FSMContext):
    if await check_first_char_city(message):
        await state.update_data(waiting_user_city=message.text)

        Menu

        city = await state.get_data()
        data = request.get_weather(city.get('waiting_city'))
        orm.create_report(message.from_user.id, data['temp'], data['condition'],
                          data['feels_like'], data['wind_speed'],
                          data['pressure_mm'], city=city)
        text = get_weather_data(city, data)
        await message.answer(text, reply_markup=Menu.markup, parse_mode='HTML')
        await state.finish()


@dp.message_handler(regexp='История')
async def get_reports(message: types.Message):
    current_page = 1
    reports = orm.get_reports(message.from_user.id)
    total_pages = math.ceil(len(reports) / 4)
    text = 'История запросов:'
    inline_markup = types.InlineKeyboardMarkup()
    for report in reports[:current_page * 4]:
        inline_markup.add(types.InlineKeyboardButton(
            text=f'{report.city} {report.date.day}.{report.date.month}.{report.date.year}',
            callback_data=f'report_{report.id}'
        ))
    current_page += 1
    inline_markup.row(
        types.InlineKeyboardButton(
            text=f'{current_page - 1}/{total_pages}',
            callback_data='None'),
        types.InlineKeyboardButton(
            text=f'Вперёд',
            callback_data=f'next_{current_page}')
    )
    await message.answer(text, reply_markup=inline_markup)


@dp.callback_query_handler(lambda call: 'users' not in call.data)
async def callback_query(call, state: FSMContext):
    query_type = call.data.split('_')[0]
    if query_type == 'delete' and call.data.split('_')[1] == 'report':
        report_id = int(call.data.split('_')[2])
        current_page = 1
        orm.delete_user_report(report_id)
        reports = orm.get_reports(call.from_user.id)
        total_pages = math.ceil(len(reports) / 4)
        inline_markup = types.InlineKeyboardMarkup()
        for report in reports[:current_page * 4]:
            inline_markup.add(types.InlineKeyboardButton(
                text=f'{report.city} {report.date.day}.{report.date.month}.{report.date.year}',
                callback_data=f'report_{report.id}'
            ))
        current_page += 1
        inline_markup.row(
            types.InlineKeyboardButton(text=f'{current_page - 1}/{total_pages}', callback_data='None'),
            types.InlineKeyboardButton(text='Вперёд', callback_data=f'next_{current_page}')
        )
        await call.message.edit_text(text='История запросов:', reply_markup=inline_markup)
        return
    async with state.proxy() as data:
        data['current_page'] = int(call.data.split('_')[1])
        await state.update_data(current_page=data['current_page'])

        if query_type == 'next':
            reports = orm.get_reports(call.from_user.id)
            total_pages = math.ceil(len(reports) / 4)
            inline_markup = types.InlineKeyboardMarkup()

            if data['current_page'] * 4 >= len(reports):
                for report in reports[data['current_page'] * 4 - 4:len(reports) + 1]:
                    inline_markup.add(types.InlineKeyboardButton(
                        text=f'{report.city} {report.date.day}.{report.date.month}.{report.date.year}',
                        callback_data=f'report_{report.id}'
                    ))
                data['current_page'] -= 1
                inline_markup.row(
                    types.InlineKeyboardButton(
                        text='Назад',
                        callback_data=f'prev_{data["current_page"]}'
                    ),
                    types.InlineKeyboardButton(
                        text=f'{data["current_page"] + 1}/{total_pages}',
                        callback_data='None'
                    )
                )
                await call.message.edit_text(text="История запросов:", reply_markup=inline_markup)
                return

            for report in reports[data['current_page'] * 4 - 4:data['current_page'] * 4]:
                inline_markup.add(types.InlineKeyboardButton(
                    text=f'{report.city} {report.date.day}.{report.date.month}.{report.date.year}',
                    callback_data=f'report_{report.id}'
                ))
            data['current_page'] += 1
            inline_markup.row(
                types.InlineKeyboardButton(
                    text='Назад',
                    callback_data=f'prev_{data["current_page"] - 2}'
                ),
                types.InlineKeyboardButton(
                    text=f'{data["current_page"] - 1}/{total_pages}',
                    callback_data='None'
                ),
                types.InlineKeyboardButton(
                    text='Вперёд',
                    callback_data=f'next_{data["current_page"]}'
                )
            )
            await call.message.edit_text(text="История запросов:", reply_markup=inline_markup)

        if query_type == 'prev':
            reports = orm.get_reports(call.from_user.id)
            total_pages = math.ceil(len(reports) / 4)
            inline_markup = types.InlineKeyboardMarkup()

            if data['current_page'] == 1:
                for report in reports[0:data['current_page'] * 4]:
                    inline_markup.add(types.InlineKeyboardButton(
                        text=f'{report.city} {report.date.day}.{report.date.month}.{report.date.year}',
                        callback_data=f'report_{report.id}'
                    ))
                data['current_page'] += 1
                inline_markup.row(
                    types.InlineKeyboardButton(
                        text=f'{data["current_page"] - 1}/{total_pages}',
                        callback_data='None'
                    ),
                    types.InlineKeyboardButton(
                        text='Вперёд',
                        callback_data=f'next_{data["current_page"]}'
                    )
                )
                await call.message.edit_text(text="История запросов:", reply_markup=inline_markup)
                return

            for report in reports[data['current_page'] * 4 - 4:data['current_page'] * 4]:
                inline_markup.add(types.InlineKeyboardButton(
                    text=f'{report.city} {report.date.day}.{report.date.month}.{report.date.year}',
                    callback_data=f'report_{report.id}'
                ))
            data['current_page'] -= 1
            inline_markup.row(
                types.InlineKeyboardButton(
                    text='Назад',
                    callback_data=f'prev_{data["current_page"]}'
                ),
                types.InlineKeyboardButton(
                    text=f'{data["current_page"] + 1}/{total_pages}',
                    callback_data='None'
                ),
                types.InlineKeyboardButton(
                    text='Вперёд',
                    callback_data=f'next_{data["current_page"]}'
                ),
            )
            await call.message.edit_text(text="История запросов:", reply_markup=inline_markup)

        if query_type == 'report':
            reports = orm.get_reports(call.from_user.id)
            report_id = call.data.split('_')[1]
            inline_markup = types.InlineKeyboardMarkup()

            for report in reports:
                if report.id == int(report_id):
                    inline_markup.add(
                        types.InlineKeyboardButton(
                            text='Назад',
                            callback_data=f'reports_{data["current_page"]}'
                        ),
                        types.InlineKeyboardButton(
                            text='Удалить зарос',
                            callback_data=f'delete_report_{report_id}'
                        )
                    )
                    await call.message.edit_text(
                        text=f'Данные по запросу\n'
                             f'Город: {report.city}\n'
                             f'Температура: {report.temp}°C\n'
                             f'Ощущается как: {report.feels_like}°C\n'
                             f'Скорость ветра: {report.wind_speed} м/с\n'
                             f'Давление: {report.pressure_mm} мм',
                        reply_markup=inline_markup
                    )
                    break

        if query_type == 'reports':
            reports = orm.get_reports(call.from_user.id)
            total_pages = math.ceil(len(reports) / 4)
            inline_markup = types.InlineKeyboardMarkup()
            data['current_page'] = 1

            for report in reports[:data['current_page'] * 4]:
                inline_markup.add(types.InlineKeyboardButton(
                    text=f'{report.city} {report.date.day}.{report.date.month}.{report.date.year}',
                    callback_data=f'report_{report.id}'
                ))
            data['current_page'] += 1
            inline_markup.row(
                types.InlineKeyboardButton(
                    text=f'{data["current_page"] - 1}/{total_pages}',
                    callback_data='None'
                ),
                types.InlineKeyboardButton(
                    text='Вперёд',
                    callback_data=f'next_{data["current_page"]}'
                )
            )
            await call.message.edit_text(text='История запросов:', reply_markup=inline_markup)


@dp.message_handler(lambda message: message.from_user.id in bot_config.tg_bot_admin
                                    and message.text == 'Администратор')
async def admin_panel(message: types.Message):
    markup = types.reply_keyboard.ReplyKeyboardMarkup(resize_keyboard=True)
    btn1 = types.KeyboardButton('Список пользователей')
    markup.add(btn1)
    text = f'Админ-панель'
    await message.answer(text, reply_markup=markup)


@dp.message_handler(
    lambda message: message.from_user.id in bot_config.tg_bot_admin
                    and message.text == 'Список пользователей')
async def get_all_users(message: types.Message):
    current_page = 1
    users = orm.get_all_users()
    total_pages = math.ceil(len(users) / 4)
    text = 'Все мои пользователи:'
    inline_markup = types.InlineKeyboardMarkup()

    for user in users[:current_page * 4]:
        inline_markup.add(types.InlineKeyboardButton(
            text=f'{user.id}) id: {user.tg_id}. Подключился: \
 {user.connection_date.day}.{user.connection_date.month}.{user.connection_date.year}. \
 Отчётов: {len(user.reports)}',
            callback_data=f'None'
        ))
    current_page += 1
    inline_markup.row(
        types.InlineKeyboardButton(text=f'{current_page - 1}/{total_pages}', callback_data='None'),
        types.InlineKeyboardButton(text='Вперёд', callback_data=f'next_users_{current_page}')
    )
    await message.answer(text, reply_markup=inline_markup)


@dp.callback_query_handler(lambda call: 'users' in call.data)
async def callback_query(call, state: FSMContext):
    query_type = call.data.split('_')[0]
    async with state.proxy() as data:
        data['current_page'] = int(call.data.split('_')[2])
        await state.update_data(current_page=data['current_page'])

        if query_type == 'next':
            users = orm.get_all_users()
            total_pages = math.ceil(len(users) / 4)
            inline_markup = types.InlineKeyboardMarkup()

            if data['current_page'] * 4 >= len(users):
                for user in users[data['current_page'] * 4 - 4:len(users) + 1]:
                    inline_markup.add(types.InlineKeyboardButton(
                        text=f'{user.id}) id: {user.tg_id}. Подключился: \
 {user.connection_date.day}.{user.connection_date.month}.{user.connection_date.year}. \
 Отчётов: {len(user.reports)}',
                        callback_data=f'None'
                    ))
                data['current_page'] -= 1
                inline_markup.row(
                    types.InlineKeyboardButton(
                        text='Назад',
                        callback_data=f'prev_users_{data["current_page"]}'
                    ),
                    types.InlineKeyboardButton(
                        text=f'{data["current_page"] + 1}/{total_pages}',
                        callback_data='None'
                    )
                )
                await call.message.edit_text(text='Все мои пользователи:', reply_markup=inline_markup)
                return

            for user in users[data['current_page'] * 4 - 4:data['current_page'] * 4]:
                inline_markup.add(types.InlineKeyboardButton(
                    text=f'{user.id}) id: {user.tg_id}. Подключился: \
 {user.connection_date.day}.{user.connection_date.month}.{user.connection_date.year}. \
 Отчётов: {len(user.reports)}',
                    callback_data=f'None'
                ))
            data['current_page'] += 1
            inline_markup.row(
                types.InlineKeyboardButton(
                    text='Назад',
                    callback_data=f'prev_users_{data["current_page"] - 2}'
                ),
                types.InlineKeyboardButton(
                    text=f'{data["current_page"] - 1}/{total_pages}',
                    callback_data='None'
                ),
                types.InlineKeyboardButton(
                    text='Вперёд',
                    callback_data=f'next_users_{data["current_page"]}'
                )
            )
            await call.message.edit_text(text='Все мои пользователи:', reply_markup=inline_markup)

        if query_type == 'prev':
            users = orm.get_all_users()
            total_pages = math.ceil(len(users) / 4)
            inline_markup = types.InlineKeyboardMarkup()

            if data['current_page'] == 1:
                for user in users[0:data['current_page'] * 4]:
                    inline_markup.add(types.InlineKeyboardButton(
                        text=f'{user.id}) id: {user.tg_id}. Подключился: \
 {user.connection_date.day}.{user.connection_date.month}.{user.connection_date.year}. \
 Отчётов: {len(user.reports)}',
                        callback_data=f'None'
                    ))
                data['current_page'] += 1
                inline_markup.row(
                    types.InlineKeyboardButton(
                        text=f'{data["current_page"] - 1}/{total_pages}',
                        callback_data='None'
                    ),
                    types.InlineKeyboardButton(
                        text='Вперёд',
                        callback_data=f'next_users_{data["current_page"]}'
                    )
                )
                await call.message.edit_text(text='Все мои пользователи:', reply_markup=inline_markup)
                return

            for user in users[data['current_page'] * 4 - 4:data['current_page'] * 4]:
                inline_markup.add(types.InlineKeyboardButton(
                    text=f'{user.id}) id: {user.tg_id}. Подключился: \
 {user.connection_date.day}.{user.connection_date.month}.{user.connection_date.year}. \
 Отчётов: {len(user.reports)}',
                    callback_data=f'None'
                ))
            data['current_page'] -= 1
            inline_markup.row(
                types.InlineKeyboardButton(
                    text='Назад',
                    callback_data=f'prev_users_{data["current_page"]}'
                ),
                types.InlineKeyboardButton
                (text=f'{data["current_page"] + 1}/{total_pages}',
                 callback_data='None'
                 ),
                types.InlineKeyboardButton(
                    text='Вперёд',
                    callback_data=f'next_users_{data["current_page"]}'
                ),
            )
            await call.message.edit_text(text='Все мои пользователи:', reply_markup=inline_markup)


if __name__ == '__main__':
    executor.start_polling(dp, skip_updates=True)
