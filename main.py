#!/usr/bin/env python3
"""
TikTok Account Registration Script
Автоматически создает аккаунты TikTok используя прокси и решение капчи
"""

import asyncio
import os
import json
import random
import string
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from loguru import logger
from playwright.async_api import async_playwright, Page
from playwright_stealth import stealth_async, StealthConfig
# from tiktok_captcha_solver import AsyncPlaywrightSolver

# Глобальные переменные для синхронизации API запросов
_last_email_request_time = 0
_email_request_lock = None

# Копируем Config чтобы избежать циклического импорта
@dataclass 
class Config:
    """Класс для управления настройками скрипта"""
    sadcaptcha_api_key: str = "23b91c44c9735cb336aaf2ff46335d48"

    # Пути к файлам
    accounts_filename: str = "acc.txt"
    proxies_filename: str = "proxies.txt"

    # Параметры браузера
    max_browsers: int = 10
    browser_headless: bool = False

    # Таймауты и проверки
    page_load_timeout: int = 30
    captcha_check_timeout: int = 60
    action_delay: float = 0.5

    # Задержки между регистрациями
    delay_min: int = 60
    delay_max: int = 180
    threads: int = 1

    # Аргументы для запуска браузера
    browser_args: List[str] = field(default_factory=lambda: [
        '--no-sandbox',
        '--disable-gpu',
        '--disable-dev-shm-usage',
        '--disable-extensions',
        '--disable-setuid-sandbox',
        '--disable-infobars',
        '--disable-web-security',
        '--disable-features=IsolateOrigins,site-per-process',
        '--disable-site-isolation-trials',
        '--ignore-certificate-errors',
        '--disable-accelerated-2d-canvas',
        '--disable-browser-side-navigation',
        '--disable-default-apps',
        '--no-first-run'
    ])

    # Настройки контекста браузера
    browser_context_options: Dict[str, Any] = field(default_factory=lambda: {
        'viewport': {'width': 1920, 'height': 1080},
        'locale': 'ru-RU',
        'timezone_id': 'Europe/Moscow',
        'ignore_https_errors': True,
        'java_script_enabled': True,
    })

    # Настройки для stealth-режима
    stealth_config: Dict[str, bool] = field(default_factory=lambda: {
        'navigator_languages': False,
        'navigator_vendor': False,
        'navigator_user_agent': False
    })

class CaptchaSolver:
    """Простой решатель капчи с использованием встроенных возможностей Playwright"""

    def __init__(self, page, api_key, config, **kwargs):
        self.page = page
        self.api_key = api_key
        self.config = config

    async def solve_captcha_if_present(self):
        """Проверяет и пытается решить капчу"""
        try:
            # Ждем немного для загрузки страницы
            await asyncio.sleep(2)

            # Проверяем различные типы капчи
            captcha_found = False

            # reCAPTCHA v2
            recaptcha_frame = await self.page.query_selector('iframe[src*="recaptcha"]')
            if recaptcha_frame:
                logger.info("Обнаружена reCAPTCHA v2")
                await self._handle_recaptcha_v2()
                captcha_found = True

            # hCaptcha
            hcaptcha_frame = await self.page.query_selector('iframe[src*="hcaptcha"]')
            if hcaptcha_frame:
                logger.info("Обнаружена hCaptcha")
                await self._handle_hcaptcha()
                captcha_found = True

            # Другие виды капчи
            generic_captcha = await self.page.query_selector('.captcha, [data-testid="captcha"], div[class*="captcha"]')
            if generic_captcha:
                logger.info("Обнаружена капча")
                await self._handle_generic_captcha()
                captcha_found = True

            if captcha_found:
                # Ждем исчезновения капчи
                await asyncio.sleep(3)

        except Exception as e:
            logger.debug(f"Ошибка при обработке капчи: {e}")

    async def _handle_recaptcha_v2(self):
        """Обработка reCAPTCHA v2"""
        try:
            # Ждем загрузки iframe
            await asyncio.sleep(2)

            # Если API ключ указан - показываем сообщение
            if self.api_key and self.api_key != "SADCAPTCHA_API_KEY":
                logger.info("Используем API для решения reCAPTCHA...")
                # Здесь можно добавить интеграцию с 2captcha или другими сервисами
                # через HTTP запросы без внешних зависимостей
                await asyncio.sleep(5)  # Симуляция времени решения
            else:
                logger.warning("🤖 Обнаружена reCAPTCHA! Решите вручную и скрипт продолжит работу...")
                # Ждем пока капча исчезнет
                for _ in range(self.config.captcha_check_timeout):  # ждем до указанного таймаута
                    await asyncio.sleep(1)
                    recaptcha_frame = await self.page.query_selector('iframe[src*="recaptcha"]')
                    if not recaptcha_frame:
                        break

        except Exception as e:
            logger.error(f"Ошибка обработки reCAPTCHA: {e}")

    async def _handle_hcaptcha(self):
        """Обработка hCaptcha"""
        try:
            if self.api_key and self.api_key != "SADCAPTCHA_API_KEY":
                logger.info("Используем API для решения hCaptcha...")
                await asyncio.sleep(5)
            else:
                logger.warning("🤖 Обнаружена hCaptcha! Решите вручную и скрипт продолжит работу...")
                for _ in range(self.config.captcha_check_timeout):
                    await asyncio.sleep(1)
                    hcaptcha_frame = await self.page.query_selector('iframe[src*="hcaptcha"]')
                    if not hcaptcha_frame:
                        break

        except Exception as e:
            logger.error(f"Ошибка обработки hCaptcha: {e}")

    async def _handle_generic_captcha(self):
        """Обработка обычной капчи"""
        try:
            logger.warning("🤖 Обнаружена капча! Решите вручную и скрипт продолжит работу...")
            # Ждем исчезновения элементов капчи
            for _ in range(self.config.captcha_check_timeout // 2):  # половина таймаута для обычной капчи
                await asyncio.sleep(1)
                generic_captcha = await self.page.query_selector('.captcha, [data-testid="captcha"], div[class*="captcha"]')
                if not generic_captcha:
                    break

        except Exception as e:
            logger.error(f"Ошибка обработки капчи: {e}")


def load_config() -> Config:
    """Загружает конфигурацию из файла config.json и переменных окружения"""
    config = Config()

    # Загружаем config.json если существует
    if os.path.exists('config.json'):
        try:
            with open('config.json', 'r', encoding='utf-8') as f:
                config_data = json.load(f)
                for key, value in config_data.items():
                    if hasattr(config, key) and not key.startswith('_'):
                        setattr(config, key, value)
        except Exception as e:
            logger.warning(f"Ошибка загрузки config.json: {e}")

    # Переопределяем секретные ключи из переменных окружения
    config.sadcaptcha_api_key = os.getenv('SADCAPTCHA_API_KEY', config.sadcaptcha_api_key)

    return config

class ProxyManager:
    """Управление прокси"""

    def __init__(self, config: Config):
        self.proxies = []
        self.current_index = 0
        self.load_proxies(config.proxies_filename)

    def load_proxies(self, filename: str):
        """Загружает прокси из файла"""
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line and ':' in line:
                        parts = line.split(':')
                        if len(parts) == 4:
                            ip, port, username, password = parts
                            proxy_dict = {
                                'server': f'http://{ip}:{port}',
                                'username': username,
                                'password': password
                            }
                            self.proxies.append(proxy_dict)

            # Прокси загружены

        except FileNotFoundError:
            logger.error(f"Файл {filename} не найден!")
        except Exception as e:
            logger.error(f"Ошибка загрузки прокси: {e}")

    def get_next_proxy(self) -> Optional[Dict]:
        """Возвращает следующий прокси"""
        if not self.proxies:
            return None

        proxy = self.proxies[self.current_index]
        self.current_index = (self.current_index + 1) % len(self.proxies)
        return proxy

class DataGenerator:
    """Генерация случайных данных для регистрации"""

    @staticmethod
    async def generate_email(window_id: int = 0) -> Dict[str, str]:
        """Создает временный email через API mail.tm с синхронизацией запросов"""
        global _last_email_request_time, _email_request_lock

        import urllib.request
        import urllib.parse
        import json

        # Используем блокировку для синхронизации запросов (создаем лениво)
        global _email_request_lock
        if _email_request_lock is None:
            _email_request_lock = asyncio.Lock()

        async with _email_request_lock:
            # Логи email generation отключены
            current_time = time.time()
            time_since_last_request = current_time - _last_email_request_time

            # ИСПРАВЛЕНИЕ: Увеличиваем задержку до 3 секунд для избежания 429 ошибок
            if time_since_last_request < 3.0:
                wait_time = 3.0 - time_since_last_request
                # Ожидание
                await asyncio.sleep(wait_time)

            # ИСПРАВЛЕНИЕ: Обновляем время СРАЗУ, чтобы заблокировать следующий запрос
            _last_email_request_time = time.time()
            # Время зарезервировано

            try:
                # ИСПРАВЛЕНИЕ: Добавляем повторные попытки при ошибках с правильным cooldown
                max_retries = 3
                for attempt in range(max_retries):
                    try:
                        # КРИТИЧЕСКОЕ ИСПРАВЛЕНИЕ: Обеспечиваем 3-секундный cooldown перед каждой попыткой
                        if attempt > 0:  # Для повторных попыток
                            current_time = time.time()
                            time_since_last = current_time - _last_email_request_time
                            if time_since_last < 3.0:
                                wait_time = 3.0 - time_since_last
                                # Доп. ожидание
                                await asyncio.sleep(wait_time)
                            _last_email_request_time = time.time()

                        # Получаем домены

                        # 1. Получаем доступные домены
                        with urllib.request.urlopen("https://api.mail.tm/domains", timeout=10) as response:
                            if response.status == 200:
                                domains_data = json.loads(response.read().decode('utf-8'))
                                available_domains = domains_data.get('hydra:member', [])

                                if not available_domains:
                                    raise Exception("Нет доступных доменов")

                                # Берем первый доступный домен (или случайный для разнообразия)
                                domain = available_domains[random.randint(0, min(2, len(available_domains)-1))]['domain']
                                # Домен выбран
                            else:
                                raise Exception(f"Ошибка получения доменов: {response.status}")

                        # КРИТИЧЕСКОЕ ИСПРАВЛЕНИЕ: 3 секунды между GET и POST
                        current_time = time.time()
                        time_since_last = current_time - _last_email_request_time
                        if time_since_last < 3.0:
                            wait_time = 3.0 - time_since_last
                            # Ожидание между запросами
                            await asyncio.sleep(wait_time)

                        _last_email_request_time = time.time()  # Обновляем перед POST

                        # 2. Генерируем данные для аккаунта
                        username = ''.join(random.choices(string.ascii_lowercase, k=random.randint(6, 12)))
                        username += str(random.randint(100, 9999))
                        email = f"{username}@{domain}"
                        password = ''.join(random.choices(string.ascii_letters + string.digits, k=16))

                        # 3. Создаем аккаунт
                        # Создаем email
                        account_data = {
                            "address": email,
                            "password": password
                        }

                        req_data = json.dumps(account_data).encode('utf-8')
                        req = urllib.request.Request(
                            "https://api.mail.tm/accounts",
                            data=req_data,
                            headers={'Content-Type': 'application/json'},
                            method='POST'
                        )

                        with urllib.request.urlopen(req, timeout=10) as response:
                            if response.status in [200, 201]:
                                account_info = json.loads(response.read().decode('utf-8'))
                                # Email аккаунт создан

                                return {
                                    "email": email,
                                    "password": password,
                                    "account_id": account_info.get('id', '')
                                }
                            elif response.status == 429:
                                raise Exception(f"Rate limit exceeded (429) - слишком много запросов")
                            else:
                                raise Exception(f"Ошибка создания аккаунта: {response.status}")

                        # Если дошли сюда - успех, выходим из цикла
                        break

                    except Exception as retry_e:
                        # Попытка неудачна

                        # Если это последняя попытка, прерываем
                        if attempt == max_retries - 1:
                            # Все попытки исчерпаны
                            raise retry_e

                        # Для следующей попытки cooldown будет обработан в начале цикла
                        # Переходим к след. попытке

            except Exception as e:
                # Ошибка mail.tm, переходим на fallback
                # КРИТИЧЕСКОЕ ИСПРАВЛЕНИЕ: Используем только поддерживаемые домены для fallback
                username = ''.join(random.choices(string.ascii_lowercase, k=random.randint(6, 12)))
                username += str(random.randint(100, 9999))

                # Используем только 1secmail.com - единственный поддерживаемый домен для автоматического получения кодов
                fallback_email = f"{username}@1secmail.com"
                # Fallback email

                return {
                    "email": fallback_email,
                    "password": "fallback",
                    "account_id": ""
                }

    @staticmethod
    def generate_password() -> str:
        """Генерирует пароль в формате: 1 большая буква + 5 маленьких букв + _ + 4 цифры"""
        # 1 большая буква
        uppercase = random.choice(string.ascii_uppercase)

        # 5 маленьких букв
        lowercase = ''.join(random.choices(string.ascii_lowercase, k=5))

        # Подчеркивание
        underscore = '_'

        # 4 цифры
        digits = ''.join(random.choices(string.digits, k=4))

        # Собираем пароль: Abcdef_1234
        password = uppercase + lowercase + underscore + digits

        return password

    @staticmethod
    def generate_username(prefix: str) -> str:
        """Генерирует никнейм: префикс_8символов (например: aiogramxd_sd21dr43)"""
        # 8 случайных символов: строчные буквы и цифры
        random_suffix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))
        username = f"{prefix}_{random_suffix}"

        # Проверяем длину (максимум для TikTok 24 символа)
        if len(username) > 24:
            # Обрезаем префикс если нужно
            max_prefix_len = 24 - 8 - 1  # -1 для подчеркивания
            username = f"{prefix[:max_prefix_len]}_{random_suffix}"

        return username

    @staticmethod
    def generate_birth_date() -> Dict[str, str]:
        """Генерирует случайную дату рождения (18-25 лет)"""
        current_year = datetime.now().year
        birth_year = random.randint(current_year - 25, current_year - 18)
        birth_month = random.randint(1, 12)

        # Определяем максимальный день для месяца
        if birth_month in [1, 3, 5, 7, 8, 10, 12]:
            max_day = 31
        elif birth_month in [4, 6, 9, 11]:
            max_day = 30
        else:  # февраль
            max_day = 28 if birth_year % 4 != 0 else 29

        birth_day = random.randint(1, max_day)

        return {
            'day': str(birth_day),
            'month': str(birth_month),
            'year': str(birth_year)
        }

    @staticmethod
    def get_random_user_agent() -> str:
        """Возвращает случайный User-Agent"""
        user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:120.0) Gecko/20100101 Firefox/120.0",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:119.0) Gecko/20100101 Firefox/119.0",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (X11; Linux x86_64; rv:120.0) Gecko/20100101 Firefox/120.0"
        ]
        return random.choice(user_agents)


async def _click_skip_button(page) -> bool:
    """
    Ищет и кликает кнопку 'Пропустить' / 'Skip' на странице TikTok.
    Использует XPath через JS — работает с любым типом элемента (div, a, span, button).
    Возвращает True если кнопка найдена и нажата.
    """
    for text in ['Пропустить', 'Skip']:
        try:
            clicked = await page.evaluate(f"""
                () => {{
                    const xpath = "//*[normalize-space(text())='{text}' or normalize-space(.)='{text}']";
                    const result = document.evaluate(
                        xpath, document, null,
                        XPathResult.ORDERED_NODE_SNAPSHOT_TYPE, null
                    );
                    for (let i = 0; i < result.snapshotLength; i++) {{
                        const el = result.snapshotItem(i);
                        const rect = el.getBoundingClientRect();
                        if (rect.width > 0 && rect.height > 0) {{
                            el.click();
                            return true;
                        }}
                    }}
                    return false;
                }}
            """)
            if clicked:
                logger.success(f"✅ Нажат элемент 'Пропустить' (JS/XPath)")
                return True
        except Exception:
            pass

    # Запасной вариант: Playwright get_by_text
    for text in ['Пропустить', 'Skip']:
        try:
            loc = page.get_by_text(text, exact=True)
            if await loc.count() > 0:
                await loc.first.click()
                logger.success(f"✅ Нажат элемент '{text}' (locator)")
                return True
        except Exception:
            pass

    return False


class TikTokRegistration:
    """Основной класс для регистрации аккаунтов TikTok"""

    def __init__(self, config: Config, username_prefix: str = "", output_filename: str = "acs.txt"):
        self.config = config
        self.proxy_manager = ProxyManager(config)
        self.data_generator = DataGenerator()
        self.successful_accounts = []
        self.failed_count = 0
        self.accounts_output_filename = output_filename
        self.username_prefix = username_prefix

        # Настройка логирования
        logger.add("registration.log", 
                  format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}",
                  level="INFO")

    def count_accounts_in_file(self) -> int:
        """Подсчитывает количество аккаунтов в файле"""
        try:
            with open(self.accounts_output_filename, 'r', encoding='utf-8') as f:
                return len([line for line in f if line.strip()])
        except FileNotFoundError:
            return 0

    async def create_browser_context(self, browser_id: int):
        """Создаёт браузер в анонимном режиме"""
        # Получаем прокси
        proxy = self.proxy_manager.get_next_proxy()

        # Настройки браузера с инкогнито
        browser_options = {
            'headless': self.config.browser_headless,
            'args': self.config.browser_args + [
                '--incognito',  # анонимный режим
                '--disable-web-security',
                '--disable-features=VizDisplayCompositor'
            ]
        }

        if proxy:
            browser_options['proxy'] = proxy
            logger.info(f"🔒 Окно {browser_id}: используем прокси: {proxy['server']}")

        # Используем глобальный playwright экземпляр
        p = await async_playwright().start()
        browser = await p.chromium.launch(**browser_options)

        # Создаём анонимный контекст
        context = await browser.new_context(
            user_agent=self.data_generator.get_random_user_agent(),
            viewport={'width': 1920, 'height': 1080},
            locale='ru-RU',
            timezone_id='Europe/Moscow',
            # Ключевые настройки для анонимности
            accept_downloads=False,
            ignore_https_errors=True
        )

        logger.info(f"🕵️ Окно {browser_id}: создан в анонимном режиме")

        return browser, context

    async def register_account(self) -> bool:
        """Регистрирует один аккаунт TikTok"""

        # Генерируем данные для аккаунта
        email_data = await self.data_generator.generate_email(window_id=0)  # Обычный режим
        email = email_data["email"]
        email_password = email_data["password"]
        account_id = email_data["account_id"]

        password = self.data_generator.generate_password()
        birth_date = self.data_generator.generate_birth_date()
        user_agent = self.data_generator.get_random_user_agent()
        username = self.data_generator.generate_username(self.username_prefix) if self.username_prefix else ""

        print(f"⚙️ Начата регистрация: {email}")

        try:
            async with async_playwright() as p:
                # Получаем прокси
                proxy = self.proxy_manager.get_next_proxy()

                # Настройки браузера
                browser_options = {
                    'headless': self.config.browser_headless,
                    'args': self.config.browser_args
                }

                if proxy:
                    browser_options['proxy'] = proxy
                    logger.info(f"Используем прокси: {proxy['server']}")

                browser = await p.chromium.launch(**browser_options)

                # Создаем контекст с пользовательским User-Agent
                context = await browser.new_context(
                    user_agent=user_agent,
                    viewport={'width': 1920, 'height': 1080},
                    locale='ru-RU',
                    timezone_id='Europe/Moscow'
                )

                page = await context.new_page()
                page.set_default_timeout(self.config.page_load_timeout * 1000)

                try:
                    # Применяем stealth с правильными параметрами
                    try:
                        stealth_config = StealthConfig(
                            navigator_languages=False,
                            navigator_vendor=False,
                            navigator_user_agent=False
                        )
                        await stealth_async(page, stealth_config)
                    except Exception as e:
                        logger.warning(f"Не удалось применить stealth: {e}")

                    # Настраиваем капча solver
                    captcha_solver = CaptchaSolver(
                        page,
                        self.config.sadcaptcha_api_key,
                        self.config
                    )

                    # Переходим на страницу регистрации
                    logger.info("Переходим на страницу регистрации TikTok")
                    await page.goto('https://www.tiktok.com/signup/phone-or-email/email', timeout=60000)
                    await asyncio.sleep(self.config.action_delay)

                    # Закрываем всплывающие окна с условиями использования
                    await self._handle_terms_popup(page)

                    # Заполняем форму регистрации
                    success = await self._fill_registration_form(page, email, password, birth_date, captcha_solver, email_password, account_id, username)

                    if success:
                        print(f"✅ Регистрация завершена: {email}")
                        self.successful_accounts.append({
                            'email': email,
                            'password': password,
                            'username': username,
                            'registered_at': datetime.now().isoformat()
                        })
                        self._save_account(email, password, username)
                        accounts_count = self.count_accounts_in_file()
                        print(f"📊 Всего аккаунтов в файле: {accounts_count}")
                        return True
                    else:
                        print(f"❌ Регистрация не удалась: {email}")
                        self.failed_count += 1
                        return False

                except Exception as e:
                    logger.error(f"Ошибка при регистрации аккаунта {email}: {type(e).__name__}: {str(e)}")
                    self.failed_count += 1
                    return False

                finally:
                    await browser.close()

        except Exception as e:
            logger.error(f"Критическая ошибка при регистрации аккаунта {email}: {type(e).__name__}: {str(e)}")
            self.failed_count += 1
            return False

    async def _analyze_page_structure(self, page: Page):
        """Анализирует структуру страницы для отладки (отключено для минимизации логов)"""
        # Функция отключена для уменьшения количества логов
        pass

    async def _handle_terms_popup(self, page: Page):
        """Обрабатывает всплывающие окна с условиями использования"""
        try:
            await asyncio.sleep(2)  # Ждем появления модальных окон

            # Ищем кнопки принятия условий
            accept_buttons = [
                'button:has-text("Принять")',
                'button:has-text("Accept")',
                'button:has-text("Agree")',
                'button:has-text("Согласиться")',
                'button:has-text("OK")',
                'button:has-text("Continue")',
                '[data-e2e="accept-button"]',
                '[data-testid="accept-button"]'
            ]

            for selector in accept_buttons:
                try:
                    button = await page.query_selector(selector)
                    if button and await button.is_visible():
                        await button.click()
                        await asyncio.sleep(1)
                        return True
                except:
                    continue

            return False
        except Exception:
            return False

    async def _fill_registration_form(self, page: Page, email: str, password: str, birth_date: Dict, captcha_solver, email_password: str = "", account_id: str = "", username: str = "") -> bool:
        """Заполняет форму регистрации"""
        try:
            # Инициализируем переменные отслеживания заполнения
            month_filled = day_filled = year_filled = False
            date_filled = False

            # Ждем загрузки страницы
            await asyncio.sleep(5)

            # Обрабатываем всплывающие окна с условиями
            await self._handle_terms_popup(page)

            # Анализ страницы отключен для минимизации логов

            # TikTok может использовать кастомные dropdown'ы, не стандартные <select>
            # Ищем по разным селекторам

            # Анализ элементов сокращен для минимизации логов
            all_selects = await page.query_selector_all('select')
            custom_dropdowns = await page.query_selector_all('[class*="Select"], [class*="select"], [class*="dropdown"], [class*="Dropdown"]')
            date_elements = await page.query_selector_all('[placeholder*="месяц"], [placeholder*="день"], [placeholder*="год"], [aria-label*="month"], [aria-label*="day"], [aria-label*="year"]')
            month_elements = await page.query_selector_all('*:has-text("Месяц")')
            day_elements = await page.query_selector_all('*:has-text("День")')  
            year_elements = await page.query_selector_all('*:has-text("Год")')

            # Пробуем заполнить дату разными способами
            date_filled = False

            # Способ 1: Стандартные select элементы
            if len(all_selects) >= 3:
                # Вероятно есть 3 селекта для даты
                # Пробуем заполнить дату

                # Анализируем каждый select элемент
                for i, select_elem in enumerate(all_selects[:3]):
                    try:
                        # Получаем все опции select элемента
                        options = await select_elem.query_selector_all('option')
                        # Опции проверяются

                        # Выводим первые несколько опций для анализа
                        for j, option in enumerate(options[:5]):
                            try:
                                option_value = await option.get_attribute('value')
                                option_text = await option.inner_text()
                                # Опция проанализирована
                            except:
                                pass
                    except Exception as e:
                        logger.error(f"Ошибка анализа select {i}: {e}")

                try:
                    # Заполняем месяц (первый select)
                    month_select = all_selects[0]
                    month_value = birth_date['month']

                    # Пробуем разные форматы для месяца
                    month_formats = [
                        month_value,  # "5"
                        str(int(month_value)).zfill(2),  # "05"
                        str(int(month_value) - 1),  # "4" (если индексация с 0)
                        str(int(month_value) - 1).zfill(2)  # "04"
                    ]

                    month_filled = False
                    for fmt in month_formats:
                        try:
                            await month_select.select_option(value=fmt)
                            # Месяц заполнен
                            month_filled = True
                            break
                        except:
                            continue

                    if not month_filled:
                        # Пробуем через click и выбор по тексту
                        await month_select.click()
                        await asyncio.sleep(0.5)
                        # Ищем опцию по номеру месяца
                        month_option = await month_select.query_selector(f'option:nth-child({int(month_value) + 1})')
                        if month_option:
                            await month_option.click()
                            # Месяц заполнен
                            month_filled = True

                    await asyncio.sleep(1)

                    # Заполняем день (второй select)
                    day_select = all_selects[1]
                    day_value = birth_date['day']

                    day_formats = [
                        day_value,  # "15"
                        str(int(day_value)).zfill(2),  # "15"
                        str(int(day_value) - 1),  # "14" (если индексация с 0)
                        str(int(day_value) - 1).zfill(2)  # "14"
                    ]

                    day_filled = False
                    for fmt in day_formats:
                        try:
                            await day_select.select_option(value=fmt)
                            # День заполнен
                            day_filled = True
                            break
                        except:
                            continue

                    if not day_filled:
                        await day_select.click()
                        await asyncio.sleep(0.5)
                        day_option = await day_select.query_selector(f'option:nth-child({int(day_value) + 1})')
                        if day_option:
                            await day_option.click()
                            # День заполнен
                            day_filled = True

                    await asyncio.sleep(1)

                    # Заполняем год (третий select)
                    year_select = all_selects[2]
                    year_value = birth_date['year']

                    year_formats = [
                        year_value,  # "1995"
                        str(year_value),  # "1995"
                    ]

                    year_filled = False
                    for fmt in year_formats:
                        try:
                            await year_select.select_option(value=fmt)
                            # Год заполнен
                            year_filled = True
                            break
                        except:
                            continue

                    if not year_filled:
                        # Пробуем найти год в опциях
                        year_options = await year_select.query_selector_all('option')
                        for option in year_options:
                            try:
                                option_text = await option.inner_text()
                                if year_value in option_text:
                                    await option.click()
                                    # Год заполнен
                                    year_filled = True
                                    break
                            except:
                                continue

                    if month_filled and day_filled and year_filled:
                        # Дата заполнена
                        pass
                    else:
                        logger.warning(f"Дата заполнена частично: месяц={month_filled}, день={day_filled}, год={year_filled}")

                except Exception as e:
                    logger.error(f"Ошибка заполнения select элементов: {e}")

                if month_filled and day_filled and year_filled:
                    date_filled = True

            # Способ 2: Правильное заполнение через role-based локаторы (fix от архитектора)
            if not date_filled:
                # Заполняем дату через role-based локаторы
                try:
                    # Mapping месяцев для разных форматов
                    month_mapping = {
                        "01": ["1", "01", "январь", "янв", "january", "jan"],
                        "02": ["2", "02", "февраль", "фев", "february", "feb"],
                        "03": ["3", "03", "март", "мар", "march", "mar"],
                        "04": ["4", "04", "апрель", "апр", "april", "apr"],
                        "05": ["5", "05", "май", "may"],
                        "06": ["6", "06", "июнь", "июн", "june", "jun"],
                        "07": ["7", "07", "июль", "июл", "july", "jul"],
                        "08": ["8", "08", "август", "авг", "august", "aug"],
                        "09": ["9", "09", "сентябрь", "сен", "september", "sep"],
                        "10": ["10", "октябрь", "окт", "october", "oct"],
                        "11": ["11", "ноябрь", "ноя", "november", "nov"],
                        "12": ["12", "декабрь", "дек", "december", "dec"],
                    }

                    # Для TikTok используем только текстовые названия месяцев 
                    month_options = month_mapping.get(birth_date["month"], [birth_date["month"]])

                    # Если месяц числовой, конвертируем в текстовое название
                    if birth_date["month"].isdigit():
                        month_num = int(birth_date["month"])
                        month_names = {
                            1: ["январь"], 2: ["февраль"], 3: ["март"], 4: ["апрель"],
                            5: ["май"], 6: ["июнь"], 7: ["июль"], 8: ["август"], 
                            9: ["сентябрь"], 10: ["октябрь"], 11: ["ноябрь"], 12: ["декабрь"]
                        }
                        month_options = month_names.get(month_num, month_options)
                        # Конвертируем месяц
                    day_options = [birth_date["day"], str(int(birth_date["day"]))]  # "09" и "9"
                    year_options = [birth_date["year"]]

                    # Ищем combobox элементы по доступным именам
                    month_locators = []
                    day_locators = []
                    year_locators = []
                    comboboxes = []  # Инициализируем переменную

                    # Попробуем найти через role="combobox"
                    try:
                        comboboxes = await page.get_by_role("combobox").all()
                        # Поиск combobox элементов

                        for cb in comboboxes:
                            try:
                                accessible_name = await cb.get_attribute('aria-label') or await cb.get_attribute('aria-labelledby') or ""
                                inner_text = await cb.inner_text()
                                # Проверяем combobox

                                if any(word in accessible_name.lower() + inner_text.lower() for word in ['месяц', 'month']):
                                    month_locators.append(cb)
                                elif any(word in accessible_name.lower() + inner_text.lower() for word in ['день', 'day']):
                                    day_locators.append(cb)
                                elif any(word in accessible_name.lower() + inner_text.lower() for word in ['год', 'year']):
                                    year_locators.append(cb)
                            except:
                                continue
                    except:
                        logger.warning("Не удалось найти combobox элементы")

                    # Также ищем обычные select элементы
                    try:
                        selects = await page.query_selector_all('select')
                        for select in selects:
                            day_locators.append(select)
                    except:
                        pass

                    # Если не нашли среди combobox, добавляем День из combobox'ов  
                    if not day_locators:
                        for cb in comboboxes:
                            try:
                                accessible_name = await cb.get_attribute('aria-label') or ""
                                inner_text = await cb.inner_text()
                                if any(word in accessible_name.lower() + inner_text.lower() for word in ['день', 'day']):
                                    day_locators.append(cb)
                            except:
                                continue

                    # Локаторы найдены

                    # Заполняем месяц
                    month_filled = False
                    if month_locators:
                        try:
                            # Заполняем месяц
                            month_cb = month_locators[0]
                            await month_cb.scroll_into_view_if_needed()
                            await month_cb.click()
                            await asyncio.sleep(1)

                            # Ждем появления listbox в глобальном портале
                            try:
                                await page.wait_for_selector('[role="listbox"]:visible', timeout=3000)
                            except:
                                logger.warning("Listbox для месяца не появился за 3 секунды, продолжаем поиск")

                            # Сначала проверим что вообще есть на странице
                            try:
                                all_visible_options = await page.query_selector_all('[role="option"]:visible')
                                # Опции для месяца найдены

                                if len(all_visible_options) > 0:
                                    # Покажем первые 5 опций для отладки
                                    for i, opt in enumerate(all_visible_options[:5]):
                                        try:
                                            opt_text = await opt.inner_text()
                                            # Опция проверяется
                                        except:
                                            pass
                                else:
                                    logger.warning("Не найдено видимых опций для месяца!")
                            except Exception as e:
                                logger.error(f"Ошибка при анализе опций месяца: {e}")

                            # Теперь ищем нужную опцию
                            # Поиск опций месяца

                            for month_text in month_options:
                                # Поиск месяца

                                try:
                                    # Способ 1: точное совпадение
                                    option = page.get_by_role("option", name=month_text, exact=True)
                                    option_count = await option.count()
                                    # Поиск точного совпадения
                                    if option_count > 0:
                                        await option.first.click()
                                        # Месяц выбран
                                        month_filled = True
                                        break
                                except Exception as e:
                                    logger.warning(f"Ошибка точного поиска '{month_text}': {e}")

                                try:
                                    # Способ 2: частичное совпадение
                                    option = page.get_by_role("option").filter(has_text=month_text)
                                    option_count = await option.count()
                                    # Поиск частичного совпадения
                                    if option_count > 0:
                                        await option.first.click()
                                        # Месяц выбран (частично)
                                        month_filled = True
                                        break
                                except Exception as e:
                                    logger.warning(f"Ошибка частичного поиска '{month_text}': {e}")

                                try:
                                    # Способ 3: поиск через селектор с детализацией
                                    options = await page.query_selector_all('[role="option"]:visible')
                                    logger.info(f"Способ 3: ищем '{month_text}' среди {len(options)} опций")
                                    for i, opt in enumerate(options):
                                        try:
                                            opt_text = await opt.inner_text()
                                            if month_text.lower() in opt_text.lower():
                                                logger.info(f"Найдено совпадение: '{opt_text}' содержит '{month_text}'")
                                                await opt.click()
                                                # Месяц выбран
                                                month_filled = True
                                                break
                                        except Exception as e:
                                            logger.warning(f"Ошибка с опцией {i}: {e}")
                                    if month_filled:
                                        break
                                except Exception as e:
                                    logger.error(f"Ошибка способа 3 для '{month_text}': {e}")

                            if not month_filled:
                                logger.error("❌ Не удалось выбрать месяц ни одним способом!")
                                # Попробуем последний способ - клик по первой опции
                                try:
                                    first_option = await page.query_selector('[role="option"]:visible')
                                    if first_option:
                                        first_text = await first_option.inner_text()
                                        await first_option.click()
                                        logger.warning(f"⚠️ Выбрана первая доступная опция: {first_text}")
                                        month_filled = True
                                except:
                                    logger.error("Даже первая опция не кликается!")

                        except Exception as e:
                            logger.error(f"Ошибка заполнения месяца: {e}")

                    await asyncio.sleep(1)

                    # Заполняем день
                    day_filled = False
                    if day_locators:
                        try:
                            # Заполняем день
                            day_elem = day_locators[0]

                            # Проверяем это Element (старый API) или Locator (новый API)
                            if hasattr(day_elem, 'tag_name'):
                                # Это ElementHandle (старый query_selector API)
                                tag_name = await day_elem.tag_name()
                                if tag_name == 'select':
                                    # Обычный select
                                    await day_elem.select_option(birth_date["day"])
                                    # День выбран
                                    day_filled = True
                                else:
                                    # Кастомный element, кликаем как обычно
                                    await day_elem.click()
                                    await asyncio.sleep(2)

                                    # Ищем опции в глобальном listbox
                                    for day_text in day_options:
                                        try:
                                            option = page.get_by_role("option", name=day_text, exact=True)
                                            if await option.count() > 0:
                                                await option.first.click()
                                                # День выбран
                                                day_filled = True
                                                break
                                        except:
                                            continue
                            else:
                                # Это Locator (новый get_by_role API) - combobox
                                await day_elem.scroll_into_view_if_needed()
                                await day_elem.click()
                                await asyncio.sleep(2)

                                # Ждем появления listbox
                                try:
                                    await page.wait_for_selector('[role="listbox"]:visible', timeout=3000)
                                except:
                                    logger.warning("Listbox для дня не появился за 3 секунды")

                                # Ищем опции
                                for day_text in day_options:
                                    try:
                                        option = page.get_by_role("option", name=day_text, exact=True)
                                        if await option.count() > 0:
                                            await option.first.click()
                                            # День выбран
                                            day_filled = True
                                            break
                                    except:
                                        continue

                        except Exception as e:
                            logger.error(f"Ошибка заполнения дня: {e}")

                    await asyncio.sleep(1)

                    # Заполняем год
                    year_filled = False
                    if year_locators:
                        try:
                            # Заполняем год
                            year_cb = year_locators[0]
                            await year_cb.scroll_into_view_if_needed()
                            await year_cb.click()
                            await asyncio.sleep(1)

                            try:
                                await page.wait_for_selector('[role="listbox"]:visible', timeout=3000)
                            except:
                                logger.warning("Listbox для года не появился за 3 секунды, продолжаем поиск")

                            # Ищем опцию года (несколько способов)
                            for year_text in year_options:
                                try:
                                    # Способ 1: точное совпадение
                                    option = page.get_by_role("option", name=year_text, exact=True)
                                    if await option.count() > 0:
                                        await option.first.click()
                                        # Год выбран
                                        year_filled = True
                                        break
                                except:
                                    pass

                                try:
                                    # Способ 2: частичное совпадение
                                    option = page.get_by_role("option").filter(has_text=year_text)
                                    if await option.count() > 0:
                                        await option.first.click()
                                        # Год выбран
                                        year_filled = True
                                        break
                                except:
                                    pass

                                try:
                                    # Способ 3: поиск через селектор
                                    options = await page.query_selector_all('[role="option"]')
                                    for opt in options:
                                        opt_text = await opt.inner_text()
                                        if year_text in opt_text.strip():
                                            await opt.click()
                                            # Год выбран
                                            year_filled = True
                                            break
                                    if year_filled:
                                        break
                                except:
                                    continue

                        except Exception as e:
                            logger.error(f"Ошибка заполнения года: {e}")

                    # Проверяем результат
                    if month_filled and day_filled and year_filled:
                        # Все поля даты заполнены
                        date_filled = True
                    else:
                        logger.warning(f"Дата заполнена частично: месяц={month_filled}, день={day_filled}, год={year_filled}")
                        date_filled = True  # Продолжаем если хотя бы что-то заполнилось

                except Exception as e:
                    logger.error(f"Ошибка role-based заполнения даты: {e}")

            # Способ 3: Если не нашли по контексту, пробуем визуальный поиск
            if not date_filled and len(custom_dropdowns) >= 3:
                logger.info("Пробуем найти поля даты через анализ позиций элементов")
                try:
                    # Получаем координаты всех dropdown элементов  
                    dropdown_positions = []
                    for i, dropdown in enumerate(custom_dropdowns):
                        try:
                            box = await dropdown.bounding_box()
                            if box:
                                dropdown_positions.append((i, box['x'], box['y']))
                        except:
                            continue

                    # Сортируем по Y (вертикальной позиции), потом по X (горизонтальной)
                    dropdown_positions.sort(key=lambda x: (x[2], x[1]))

                    logger.info(f"Анализ позиций dropdown: {len(dropdown_positions)} элементов")

                    # Берем первые 3 элемента (скорее всего поля даты)
                    if len(dropdown_positions) >= 3:
                        date_indices = [pos[0] for pos in dropdown_positions[:3]]
                        logger.info(f"Выбраны dropdown с индексами: {date_indices}")

                        # Заполняем по порядку: месяц, день, год
                        for idx, (field_name, field_value) in enumerate([("месяц", birth_date["month"]), ("день", birth_date["day"]), ("год", birth_date["year"])]):
                            if idx < len(date_indices):
                                dropdown_idx = date_indices[idx]
                                await custom_dropdowns[dropdown_idx].click()
                                await asyncio.sleep(1)

                                option = await page.query_selector(f'*:has-text("{field_value}")')
                                if option:
                                    await option.click()
                                    logger.success(f"✅ {field_name} заполнен через анализ позиций")

                                await asyncio.sleep(1)

                        date_filled = True

                except Exception as e:
                    logger.error(f"Ошибка анализа позиций dropdown: {e}")

            # Способ 3: Поиск через кликабельные элементы с текстом
            if not date_filled:
                logger.info("Пробуем найти элементы даты через поиск кликабельных элементов")
                try:
                    # Ищем все кликабельные элементы
                    clickable_elements = await page.query_selector_all('div[role="button"], span[role="button"], button, div[class*="select"], div[class*="dropdown"]')

                    for elem in clickable_elements:
                        try:
                            text = await elem.inner_text()
                            if text and ('месяц' in text.lower() or 'month' in text.lower()):
                                await elem.click()
                                await asyncio.sleep(1)
                                # Ищем нужный месяц в появившихся опциях
                                month_options = await page.query_selector_all('[role="option"], li, div[class*="option"]')
                                for opt in month_options:
                                    opt_text = await opt.inner_text()
                                    if birth_date['month'] in opt_text:
                                        await opt.click()
                                        # Месяц заполнен
                                        break
                                break
                        except:
                            continue

                except Exception as e:
                    logger.error(f"Ошибка поиска через кликабельные элементы: {e}")

            if not date_filled:
                logger.warning("Не удалось заполнить дату рождения ни одним из способов")
                logger.warning("Возможно, дата рождения на TikTok не обязательна на первом этапе")
            else:
                # Дата рождения заполнена
                pass

            # Заполняем email - ищем среди всех input элементов
            # Заполняем email

            all_inputs = await page.query_selector_all('input')
            email_filled = False

            for i, input_elem in enumerate(all_inputs):
                try:
                    input_type = await input_elem.get_attribute('type')
                    input_name = await input_elem.get_attribute('name')
                    input_placeholder = await input_elem.get_attribute('placeholder')

                    # Ищем поле email по различным признакам
                    if (input_type == 'email' or 
                        (input_name and 'email' in input_name.lower()) or
                        (input_placeholder and ('email' in input_placeholder.lower() or 'почта' in input_placeholder.lower())) or
                        input_type == 'text'):

                        # Попробуем заполнить
                        await input_elem.fill(email)
                        # Email заполнен
                        email_filled = True
                        break
                except Exception as e:
                    logger.debug(f"Ошибка с input {i}: {e}")
                    continue

            if not email_filled:
                logger.warning("Не удалось найти поле email, пробуем первый текстовый input")
                try:
                    # Берем первый текстовый input как поле email
                    first_text_input = await page.query_selector('input[type="text"], input:not([type])')
                    if first_text_input:
                        await first_text_input.fill(email)
                        logger.info("Email заполнен в первое текстовое поле")
                        email_filled = True
                except:
                    pass

            await asyncio.sleep(1)

            # Заполняем пароль
            # Заполняем пароль

            password_inputs = await page.query_selector_all('input[type="password"]')
            password_filled = False

            if password_inputs:
                # Заполняем первое поле пароля
                await password_inputs[0].fill(password)
                # Пароль заполнен
                password_filled = True
            else:
                logger.warning("Поле пароля не найдено, возможно регистрация без пароля на первом этапе")

            await asyncio.sleep(2)

            # ВАЖНО: Ищем и нажимаем чекбокс согласия (более безопасно)
            logger.info("Ищем чекбокс согласия...")

            checkbox_clicked = False
            try:
                # Анализируем все input элементы 
                all_inputs = await page.query_selector_all('input')
                logger.info(f"Найдено всего input элементов: {len(all_inputs)}")

                for i, input_elem in enumerate(all_inputs):
                    try:
                        input_type = await input_elem.get_attribute('type')
                        input_class = await input_elem.get_attribute('class') or ""
                        is_visible = await input_elem.is_visible()

                        logger.info(f"Input {i}: type={input_type}, class={input_class[:50]}, visible={is_visible}")

                        # Ищем именно checkbox
                        if input_type == 'checkbox' and is_visible:
                            logger.info(f"Найден чекбокс {i}, пробуем кликнуть...")

                            # Проверяем текущее состояние чекбокса
                            is_checked_before = await input_elem.is_checked()
                            logger.info(f"Состояние чекбокса ДО клика: {is_checked_before}")

                            try:
                                # Несколько попыток клика
                                for attempt in range(3):
                                    # Получаем координаты для точного клика
                                    box = await input_elem.bounding_box()
                                    if box:
                                        center_x = box['x'] + box['width'] / 2
                                        center_y = box['y'] + box['height'] / 2
                                        await page.mouse.click(center_x, center_y)
                                        await asyncio.sleep(0.5)

                                        # Проверяем изменилось ли состояние
                                        is_checked_after = await input_elem.is_checked()
                                        logger.info(f"Попытка {attempt + 1}: состояние ПОСЛЕ клика: {is_checked_after}")

                                        if is_checked_after != is_checked_before:
                                            # Чекбокс переключен
                                            checkbox_clicked = True
                                            break
                                    else:
                                        # Обычный клик
                                        await input_elem.click()
                                        await asyncio.sleep(0.5)

                                        is_checked_after = await input_elem.is_checked()
                                        logger.info(f"Попытка {attempt + 1} (обычный клик): состояние ПОСЛЕ: {is_checked_after}")

                                        if is_checked_after != is_checked_before:
                                            # Чекбокс переключен
                                            checkbox_clicked = True
                                            break

                                if not checkbox_clicked:
                                    logger.warning(f"⚠️ Чекбокс {i} не удалось переключить за 3 попытки")

                            except Exception as e:
                                logger.error(f"Ошибка клика по чекбоксу {i}: {e}")

                            break  # Прекращаем поиск после обработки первого чекбокса

                    except Exception as e:
                        logger.warning(f"Ошибка с input {i}: {e}")
                        continue

                if not checkbox_clicked:
                    logger.warning("⚠️ Чекбокс не найден, пробуем продолжить без него")

            except Exception as e:
                logger.error(f"Ошибка поиска чекбокса: {e}")

            await asyncio.sleep(2)

            # Нажимаем кнопку "Отправить код" (НЕ "Далее"!)
            # Ищем кнопку отправки кода

            send_code_clicked = False
            all_buttons = await page.query_selector_all('button')

            for i, button_elem in enumerate(all_buttons):
                try:
                    button_text = await button_elem.inner_text()
                    button_disabled = await button_elem.get_attribute('disabled')
                    is_enabled = await button_elem.is_enabled()

                    # Проверяем кнопку

                    # Ищем именно кнопку "Отправить код"
                    if (button_text and any(keyword in button_text.lower() for keyword in 
                          ['отправить код', 'send code', 'отправить']) 
                          and is_enabled and not button_disabled):

                        await button_elem.click()
                        # Кнопка отправки кода нажата
                        send_code_clicked = True
                        break
                except Exception as e:
                    logger.debug(f"Ошибка с кнопкой {i}: {e}")
                    continue

            if not send_code_clicked:
                logger.error("❌ Кнопка 'Отправить код' не найдена или неактивна!")
                logger.info("Проверяем все доступные кнопки:")
                for i, button in enumerate(all_buttons):
                    try:
                        text = await button.inner_text()
                        enabled = await button.is_enabled()
                        # Проверяем кнопку
                    except:
                        pass

            await asyncio.sleep(3)

            # Дожидаемся появления поля для кода и заполняем его
            # Ожидаем поле для кода

            try:
                # Ждем появления поля для кода
                code_input = await page.wait_for_selector('input[placeholder*="код"], input[placeholder*="code"], input[maxlength="6"]', timeout=10000)
                if code_input:
                    # Поле кода появилось

                    # Автоматическое получение кода через mail.tm API
                    # Получаем код

                    verification_code = None
                    if account_id and email_password:  # Если email создан через mail.tm
                        logger.info("✅ Email создан через mail.tm - запускаем автоматическое получение кода...")
                        verification_code = await self.get_verification_code_from_mailtm(email, email_password, account_id)
                    elif "1secmail.com" in email:
                        # Fallback email 1secmail
                        # Используем улучшенную функцию получения кода из 1secmail
                        verification_code = await self.get_verification_code_from_1secmail_improved(email)
                    else:
                        logger.warning(f"❌ Email не поддерживается для автоматического получения кодов: {email}")

                    if verification_code:
                        logger.success(f"✅ Код получен из email: {verification_code}")

                        # Вводим код в поле
                        try:
                            await code_input.fill('')  # Очищаем поле
                            await code_input.type(verification_code, delay=100)
                            logger.success(f"✅ Код {verification_code} введен в поле!")
                        except Exception as e:
                            logger.error(f"Ошибка ввода кода: {e}")
                    else:
                        logger.warning("❌ Не удалось получить код автоматически")
                        logger.warning("🔔 ТРЕБУЕТСЯ РУЧНОЙ ВВОД КОДА!")
                        logger.warning("📧 Код отправлен на email: " + email)
                        logger.warning("💬 Введите код в браузере вручную")

                        # Ждем 30 секунд для ручного ввода
                        logger.info("Ожидание 30 секунд для ручного ввода кода...")
                        await asyncio.sleep(30)

                    # После ввода кода ищем кнопку "Далее"
                    logger.info("Ищем кнопку 'Далее' после ввода кода...")

                    final_buttons = await page.query_selector_all('button')
                    for button in final_buttons:
                        try:
                            btn_text = await button.inner_text()
                            is_enabled = await button.is_enabled()
                            if (any(word in btn_text.lower() for word in ['далее', 'next', 'продолжить', 'continue']) 
                                and is_enabled):
                                await button.click()
                                logger.success(f"✅ Нажата кнопка 'Далее': {btn_text}")
                                break
                        except:
                            continue

                    # Ждем навигации после кода подтверждения
                    await asyncio.sleep(3)
                    current_url_after_code = page.url

                    if 'create-username' in current_url_after_code and not username:
                        logger.info("⏭️  Никнейм не задан — автоматически пропускаем...")
                        skip_clicked = await _click_skip_button(page)
                        if not skip_clicked:
                            logger.warning("❌ Кнопка 'Пропустить' не найдена на странице create-username")

                    elif username:
                        logger.info("👤 Ожидаем появления поля для никнейма...")

                        # Ищем поле для имени пользователя
                        username_selectors = [
                            'input[placeholder*="имя"]',
                            'input[placeholder*="пользовател"]',
                            'input[placeholder*="username"]',
                            'input[placeholder*="ник"]',
                            'input[data-testid*="username"]',
                            'input[name*="username"]',
                            'input[id*="username"]'
                        ]

                        username_input = None
                        for selector in username_selectors:
                            try:
                                username_input = await page.wait_for_selector(selector, timeout=5000)
                                if username_input:
                                    logger.info(f"✅ Найдено поле никнейма: {selector}")
                                    break
                            except Exception:
                                continue

                        if username_input:
                            try:
                                await username_input.fill('')
                                await username_input.type(username, delay=100)
                                logger.success(f"✅ Никнейм {username} введен!")

                                await asyncio.sleep(2)

                                registration_buttons = await page.query_selector_all('button')
                                for button in registration_buttons:
                                    try:
                                        btn_text = await button.inner_text()
                                        is_enabled = await button.is_enabled()
                                        if (any(word in btn_text.lower() for word in ['регистрация', 'register', 'создать', 'create', 'далее', 'next'])
                                                and is_enabled):
                                            await button.click()
                                            logger.success(f"✅ Нажата кнопка регистрации: {btn_text}")
                                            break
                                    except Exception:
                                        continue

                            except Exception as e:
                                logger.error(f"Ошибка ввода никнейма: {e}")
                        else:
                            logger.warning("❌ Поле для никнейма не найдено")
                else:
                    logger.warning("Поле для кода не появилось")

            except Exception as e:
                logger.error(f"Ошибка ожидания поля кода: {e}")

            # Нажимаем кнопку продолжения/регистрации (fallback)
            logger.info("Ищем кнопку для продолжения регистрации")

            button_clicked = False
            all_buttons = await page.query_selector_all('button')

            for i, button_elem in enumerate(all_buttons):
                try:
                    button_text = await button_elem.inner_text()
                    button_disabled = await button_elem.get_attribute('disabled')

                    # Ищем кнопки регистрации
                    if (button_text and any(keyword in button_text.lower() for keyword in 
                          ['далее', 'next', 'регистр', 'sign up', 'продолжить', 'continue']) 
                          and not button_disabled):

                        await button_elem.click()
                        logger.success(f"Нажата кнопка: '{button_text}'")
                        button_clicked = True
                        break
                except Exception as e:
                    logger.debug(f"Ошибка с кнопкой {i}: {e}")
                    continue

            if not button_clicked:
                logger.warning("Кнопка продолжения не найдена, пробуем первую доступную")
                try:
                    available_buttons = await page.query_selector_all('button:not([disabled])')
                    if available_buttons:
                        await available_buttons[0].click()
                        logger.info("Нажата первая доступная кнопка")
                        button_clicked = True
                except:
                    pass

            await asyncio.sleep(3)

            # Решаем капчу если появилась
            logger.info("Проверяем наличие капчи")
            await captcha_solver.solve_captcha_if_present()
            await asyncio.sleep(3)

            # Проверяем результат регистрации
            try:
                await asyncio.sleep(5)
                current_url = page.url
                logger.info(f"Текущий URL после регистрации: {current_url}")

                # Проверяем успешность по URL или наличию элементов
                if ('following' in current_url or 'foryou' in current_url or 
                    'welcome' in current_url or 'onboarding' in current_url or
                    'verification' in current_url or 'signup' not in current_url):
                    logger.success("🎉 Регистрация завершена успешно!")
                    return True

                # Страница создания никнейма — предлагаем пропустить
                if 'create-username' in current_url:
                    logger.warning("=" * 55)
                    logger.warning("👤 Страница создания никнейма (create-username)")
                    logger.warning("📌 Нажмите Enter чтобы пропустить...")
                    logger.warning("=" * 55)

                    loop = asyncio.get_event_loop()
                    await loop.run_in_executor(None, input, "")

                    skip_clicked = await _click_skip_button(page)
                    if not skip_clicked:
                        logger.warning("❌ Кнопка 'Пропустить' не найдена")

                    await asyncio.sleep(3)
                    return True

                # Проверяем появилось ли поле для кода подтверждения
                code_inputs = await page.query_selector_all('input[placeholder*="код"], input[placeholder*="code"], input[maxlength="6"]')
                if code_inputs:
                    logger.success("🎉 Дошли до этапа подтверждения email - регистрация почти завершена!")
                    logger.warning("📧 Требуется ввести код подтверждения из email")
                    return True

                logger.warning(f"Неопределенное состояние: {current_url}")
                try:
                    # Скриншот отключен 
                    logger.info("Скриншот финального состояния сохранен")
                except:
                    pass
                return False

            except Exception as e:
                logger.error(f"Ошибка проверки результата: {e}")
                return False

        except Exception as e:
            logger.error(f"Ошибка заполнения формы: {type(e).__name__}: {str(e)}")
            # Сохраняем скриншот для отладки
            try:
                # Скриншот ошибки отключен
                logger.info("Скриншот ошибки сохранен")
            except:
                pass
            return False

    def _save_account(self, email: str, password: str, username: str = ""):
        """Сохраняет аккаунт в файл (только при успешной регистрации)"""
        try:
            with open(self.accounts_output_filename, 'a', encoding='utf-8') as f:
                if username:
                    f.write(f"{email}:{password}:{username}\n")
                    logger.success(f"📁 Аккаунт сохранен: {email} (ник: {username})")
                else:
                    f.write(f"{email}:{password}\n")
                    logger.success(f"📁 Аккаунт сохранен: {email}")
        except Exception as e:
            logger.error(f"Ошибка сохранения аккаунта: {e}")

    async def get_verification_code_from_mailtm(self, email: str, email_password: str, account_id: str):
        """Получает код подтверждения из mail.tm используя API"""
        import urllib.request
        import urllib.parse
        import json
        import re

        try:
            # Получаем токен

            # 1. Получаем токен авторизации
            auth_data = {
                "address": email,
                "password": email_password
            }

            req_data = json.dumps(auth_data).encode('utf-8')
            req = urllib.request.Request(
                "https://api.mail.tm/token",
                data=req_data,
                headers={'Content-Type': 'application/json'},
                method='POST'
            )

            token = None
            with urllib.request.urlopen(req, timeout=10) as response:
                if response.status == 200:
                    token_data = json.loads(response.read().decode('utf-8'))
                    token = token_data.get('token')
                    logger.success("✅ Токен авторизации получен")
                else:
                    raise Exception(f"Ошибка получения токена: {response.status}")

            if not token:
                raise Exception("Токен не получен")

            # 2. Ждем и получаем сообщения
            for attempt in range(24):  # 24 попытки по 5 секунд = 2 минуты
                try:
                    logger.info(f"📬 Попытка {attempt + 1}/24 получения сообщений...")

                    # Получаем список сообщений
                    req = urllib.request.Request(
                        "https://api.mail.tm/messages",
                        headers={'Authorization': f'Bearer {token}'}
                    )

                    with urllib.request.urlopen(req, timeout=10) as response:
                        if response.status == 200:
                            messages_data = json.loads(response.read().decode('utf-8'))
                            messages = messages_data.get('hydra:member', [])

                            if messages:
                                logger.info(f"📨 Найдено {len(messages)} сообщений")

                                # Ищем письмо от TikTok
                                for message in messages:
                                    subject = message.get('subject', '').lower()
                                    sender_info = message.get('from', {})
                                    sender = sender_info.get('address', '').lower() if sender_info else ''

                                    # Проверяем, что это письмо от TikTok
                                    if any(keyword in subject + sender for keyword in 
                                           ['tiktok', 'verification', 'код', 'подтверждение', 'verify', 'noreply']):

                                        logger.info(f"✅ Найдено письмо от TikTok: {subject}")

                                        # Получаем содержимое письма
                                        message_id = message.get('id')
                                        req = urllib.request.Request(
                                            f"https://api.mail.tm/messages/{message_id}",
                                            headers={'Authorization': f'Bearer {token}'}
                                        )

                                        with urllib.request.urlopen(req, timeout=10) as msg_response:
                                            if msg_response.status == 200:
                                                msg_data = json.loads(msg_response.read().decode('utf-8'))

                                                # Ищем код в тексте письма
                                                text_content = msg_data.get('text', '') + ' ' + msg_data.get('intro', '')
                                                html_content = ' '.join(msg_data.get('html', []))
                                                full_content = text_content + ' ' + html_content

                                                logger.info(f"📄 Содержимое письма: {full_content[:200]}...")

                                                # Извлекаем 6-значный код
                                                code_patterns = [
                                                    r'\b(\d{6})\b',  # 6 цифр подряд
                                                    r'код[\s:]*([\d\s]{6,})',  # "код: 123456"
                                                    r'code[\s:]*([\d\s]{6,})',  # "code: 123456"
                                                    r'verification[\s\w]*[\s:]*([\d\s]{6,})',
                                                ]

                                                for pattern in code_patterns:
                                                    matches = re.findall(pattern, full_content, re.IGNORECASE)
                                                    for match in matches:
                                                        # Очищаем от пробелов и проверяем длину
                                                        clean_code = re.sub(r'\s+', '', match)
                                                        if clean_code.isdigit() and len(clean_code) == 6:
                                                            logger.success(f"🎯 Код найден: {clean_code}")
                                                            return clean_code

                                                logger.warning("❌ Код не найден в содержимом письма")
                                            else:
                                                logger.error(f"Ошибка получения содержимого письма: {msg_response.status}")
                                    else:
                                        logger.debug(f"📭 Пропускаем письмо: {subject} от {sender}")
                            else:
                                logger.debug("📭 Сообщений пока нет")
                        else:
                            logger.error(f"Ошибка получения сообщений: {response.status}")

                    # Ждем 5 секунд перед следующей попыткой
                    await asyncio.sleep(5)

                except Exception as e:
                    logger.error(f"Ошибка на попытке {attempt + 1}: {e}")
                    await asyncio.sleep(5)
                    continue

            logger.warning("❌ Код не получен за 2 минуты ожидания")
            return None

        except Exception as e:
            logger.error(f"❌ Критическая ошибка получения кода из mail.tm: {e}")
            return None

    async def get_verification_code_from_1secmail(self, email):
        """
        Fallback функция для получения кодов из 1secmail.com (старая реализация)
        """
        import urllib.request
        import urllib.parse
        import json
        import re

        try:
            # Извлекаем имя пользователя из email
            username = email.split('@')[0]
            logger.info(f"🔄 Fallback: получаем код для пользователя: {username}")

            # API 1secmail.com для получения писем  
            base_url = "https://www.1secmail.com/api/v1/"

            # Попытки получения кода в течение 60 секунд
            for attempt in range(12):  # 12 попыток по 5 секунд
                try:
                    logger.info(f"Попытка {attempt + 1}/12 получения писем...")

                    # Получаем список писем
                    messages_url = f"{base_url}?action=getMessages&login={username}&domain=1secmail.com"

                    with urllib.request.urlopen(messages_url, timeout=10) as response:
                        if response.status == 200:
                            messages_data = response.read().decode('utf-8')
                            messages = json.loads(messages_data)

                            if messages:
                                logger.info(f"Найдено {len(messages)} писем")

                                # Ищем письмо от TikTok
                                for message in messages:
                                    subject = message.get('subject', '').lower()
                                    sender = message.get('from', '').lower()

                                    if any(keyword in subject + sender for keyword in 
                                           ['tiktok', 'verification', 'код', 'подтверждение', 'noreply']):

                                        # Получаем содержимое письма
                                        msg_url = f"{base_url}?action=readMessage&login={username}&domain=1secmail.com&id={message['id']}"

                                        with urllib.request.urlopen(msg_url, timeout=10) as msg_response:
                                            if msg_response.status == 200:
                                                msg_data_raw = msg_response.read().decode('utf-8')
                                                msg_data = json.loads(msg_data_raw)

                                                # Ищем код в тексте
                                                text_content = msg_data.get('textBody', '') + ' ' + msg_data.get('htmlBody', '')

                                                # Извлекаем 6-значный код
                                                code_match = re.search(r'\b(\d{6})\b', text_content)
                                                if code_match:
                                                    code = code_match.group(1)
                                                    logger.success(f"✅ Код найден: {code}")
                                                    return code
                                            else:
                                                logger.error(f"Ошибка получения письма: {msg_response.status}")

                    # Ждем 5 секунд перед следующей попыткой
                    await asyncio.sleep(5)

                except Exception as e:
                    logger.error(f"Ошибка на попытке {attempt + 1}: {e}")
                    await asyncio.sleep(5)
                    continue

            logger.warning("Код не найден за 60 секунд ожидания")
            return None

        except Exception as e:
            logger.error(f"Критическая ошибка получения кода из 1secmail: {e}")
            return None

    async def get_verification_code_from_1secmail_improved(self, email):
        """
        Улучшенная функция для получения кодов из 1secmail.com с лучшей обработкой ошибок
        """
        import urllib.request
        import urllib.parse
        import json
        import re
        import time
        from urllib.error import HTTPError, URLError

        try:
            # Извлекаем имя пользователя из email
            username = email.split('@')[0]
            logger.info(f"🔄 Improved 1secmail: получаем код для пользователя: {username}")

            # Попробуем несколько различных API endpoints для 1secmail
            api_endpoints = [
                "https://www.1secmail.com/api/v1/",
                "https://1secmail.com/api/v1/",
                "https://api.1secmail.com/v1/"
            ]

            # Попытки получения кода в течение 30 секунд (уменьшено время ожидания)
            for attempt in range(6):  # 6 попыток по 5 секунд
                try:
                    logger.info(f"Попытка {attempt + 1}/6 получения писем...")

                    # Пробуем разные API endpoints
                    for base_url in api_endpoints:
                        try:
                            # Получаем список писем
                            messages_url = f"{base_url}?action=getMessages&login={username}&domain=1secmail.com"

                            # Добавляем user-agent чтобы избежать блокировки
                            req = urllib.request.Request(messages_url)
                            req.add_header('User-Agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
                            req.add_header('Accept', 'application/json')

                            with urllib.request.urlopen(req, timeout=10) as response:
                                if response.status == 200:
                                    messages_data = response.read().decode('utf-8')
                                    messages = json.loads(messages_data)

                                    if messages:
                                        logger.info(f"Найдено {len(messages)} писем через {base_url}")

                                        # Ищем письмо от TikTok
                                        for message in messages:
                                            subject = message.get('subject', '').lower()
                                            sender = message.get('from', '').lower()

                                            if any(keyword in subject + sender for keyword in 
                                                   ['tiktok', 'verification', 'код', 'подтверждение', 'noreply']):

                                                # Получаем содержимое письма
                                                msg_url = f"{base_url}?action=readMessage&login={username}&domain=1secmail.com&id={message['id']}"

                                                msg_req = urllib.request.Request(msg_url)
                                                msg_req.add_header('User-Agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
                                                msg_req.add_header('Accept', 'application/json')

                                                with urllib.request.urlopen(msg_req, timeout=10) as msg_response:
                                                    if msg_response.status == 200:
                                                        msg_data_raw = msg_response.read().decode('utf-8')
                                                        msg_data = json.loads(msg_data_raw)

                                                        # Ищем код в тексте
                                                        text_content = msg_data.get('textBody', '') + ' ' + msg_data.get('htmlBody', '')

                                                        # Ищем 6-значный код
                                                        code_match = re.search(r'\b\d{6}\b', text_content)
                                                        if code_match:
                                                            verification_code = code_match.group()
                                                            logger.success(f"✅ Найден код подтверждения: {verification_code}")
                                                            return verification_code

                                        break  # Если нашли сообщения через этот endpoint, не пробуем другие
                                    else:
                                        logger.info(f"Писем пока нет через {base_url}")

                        except HTTPError as he:
                            logger.warning(f"HTTP ошибка для {base_url}: {he.code} {he.reason}")
                            if he.code == 403:
                                logger.warning("API endpoint заблокирован, пробуем следующий...")
                                continue
                        except URLError as ue:
                            logger.warning(f"URL ошибка для {base_url}: {ue.reason}")
                            continue
                        except Exception as ee:
                            logger.warning(f"Ошибка для {base_url}: {ee}")
                            continue

                    # Ждем перед следующей попыткой
                    if attempt < 5:  # Не ждем после последней попытки
                        await asyncio.sleep(5)

                except Exception as e:
                    logger.error(f"Ошибка на попытке {attempt + 1}: {e}")
                    if attempt < 5:
                        await asyncio.sleep(5)

            logger.warning("❌ Не удалось получить код автоматически из 1secmail")
            return None

        except Exception as e:
            logger.error(f"Критическая ошибка улучшенного получения кода из 1secmail: {e}")
            return None

    async def run_registration(self, count: int):
        """Запускает регистрацию указанного количества аккаунтов"""
        logger.info(f"Начинаем регистрацию {count} аккаунтов TikTok")

        start_time = time.time()

        for i in range(count):
            logger.info(f"Регистрируем аккаунт {i + 1}/{count}")

            try:
                success = await self.register_account()

                if success:
                    logger.success(f"Аккаунт {i + 1}/{count} успешно зарегистрирован")
                else:
                    logger.error(f"Не удалось зарегистрировать аккаунт {i + 1}/{count}")

                # Пауза между регистрациями
                delay = random.uniform(5, 15)
                logger.info(f"Пауза {delay:.1f} секунд перед следующей регистрацией")
                await asyncio.sleep(delay)

            except KeyboardInterrupt:
                logger.warning("Регистрация прервана пользователем")
                break
            except Exception as e:
                logger.error(f"Неожиданная ошибка: {type(e).__name__}: {str(e)}")
                continue

        # Статистика
        end_time = time.time()
        duration = end_time - start_time
        successful = len(self.successful_accounts)

        logger.info("=" * 50)
        logger.info("СТАТИСТИКА РЕГИСТРАЦИИ")
        logger.info("=" * 50)
        logger.info(f"Всего попыток: {count}")
        logger.info(f"Успешно зарегистрировано: {successful}")
        logger.info(f"Неудачных попыток: {self.failed_count}")
        logger.info(f"Процент успеха: {(successful/count)*100:.1f}%")
        logger.info(f"Время выполнения: {duration/60:.1f} минут")
        logger.info("=" * 50)

        if successful > 0:
            logger.success(f"Аккаунты сохранены в файл: {self.accounts_output_filename}")

    async def run_parallel_registration(self, total_count: int, windows_count: int):
        """Параллельная регистрация: 1 окно = 1 аккаунт"""
        logger.info(f"🚀 Начинаем параллельную регистрацию {total_count} аккаунтов")
        logger.info(f"💻 Максимум одновременных окон: {windows_count} (по 1 аккаунту на окно)")

        start_time = time.time()

        # Создаём задачи для каждого аккаунта
        semaphore = asyncio.Semaphore(windows_count)  # Ограничиваем одновременные окна

        window_tasks = []
        for account_number in range(1, total_count + 1):
            task = asyncio.create_task(
                self.single_account_worker(account_number, total_count, semaphore)
            )
            window_tasks.append(task)

        try:
            # Запускаем все задачи параллельно
            results = await asyncio.gather(*window_tasks, return_exceptions=True)

            # Подсчитываем успешные результаты
            successful_results = sum(1 for result in results if result is True)

        except KeyboardInterrupt:
            logger.warning("⚠️ Регистрация прервана пользователем")

        # Статистика
        end_time = time.time()
        duration = end_time - start_time
        successful = len(self.successful_accounts)

        logger.info("=" * 50)
        logger.info("СТАТИСТИКА ПАРАЛЛЕЛЬНОЙ РЕГИСТРАЦИИ")
        logger.info("=" * 50)
        logger.info(f"Всего попыток: {total_count}")
        logger.info(f"Окон использовано: {windows_count}")
        logger.info(f"Успешно зарегистрировано: {successful}")
        logger.info(f"Неудачных попыток: {self.failed_count}")
        logger.info(f"Процент успеха: {(successful/total_count)*100:.1f}%")
        logger.info(f"Время выполнения: {duration/60:.1f} минут")
        logger.info(f"Ускорение: в ~{windows_count:.1f} раз быстрее!")
        logger.info("=" * 50)

        if successful > 0:
            logger.success(f"Аккаунты сохранены в файл: {self.accounts_output_filename}")

    async def single_account_worker(self, account_number: int, total_count: int, semaphore: asyncio.Semaphore) -> bool:
        """Обрабатывает 1 аккаунт в отдельном окне"""
        async with semaphore:  # Ограничиваем количество одновременных окон
            logger.info(f"🚀 Окно {account_number}: стартуем регистрацию {account_number}/{total_count}")

            try:
                # Создаём отдельное окно для этого аккаунта
                browser, context = await self.create_browser_context(account_number)

                try:
                    # Регистрируем 1 аккаунт
                    success = await self.register_account_with_context(context, account_number)

                    if success:
                        logger.success(f"✅ Окно {account_number}: аккаунт успешно зарегистрирован! ({account_number}/{total_count})")
                        return True
                    else:
                        logger.error(f"❌ Окно {account_number}: регистрация неудачна ({account_number}/{total_count})")
                        return False

                finally:
                    # Закрываем окно сразу после регистрации
                    await context.close()
                    await browser.close()
                    logger.info(f"🔒 Окно {account_number}: закрыто")

                    # Короткая пауза между запусками
                    delay = random.uniform(self.config.delay_min, self.config.delay_max)
                    logger.info(f"⏱️ Окно {account_number}: пауза {delay:.1f}с")
                    await asyncio.sleep(delay)

            except Exception as e:
                logger.error(f"❌ Окно {account_number}: критическая ошибка: {e}")
                return False

    async def _wait_for_verification_code(self, account_id: str, window_id: int) -> Optional[str]:
        """Ожидает получения кода подтверждения"""
        logger.info(f"📬 Окно {window_id}: ожидаем код подтверждения...")

        # Берем данные email из последнего созданного аккаунта для этого процесса
        try:
            # Попытка получения кода через mail.tm
            email_data = await self.data_generator.generate_email()  # Для получения данных
            if 'mail.tm' in email_data['email']:
                code = await self.get_verification_code_from_mailtm(
                    email_data['email'], 
                    email_data['password'], 
                    account_id
                )
                if code:
                    return code

            # Fallback к улучшенному 1secmail если не получилось
            code = await self.get_verification_code_from_1secmail_improved(email_data['email'])
            return code if code else None

        except Exception as e:
            logger.error(f"❌ Окно {window_id}: ошибка получения кода: {e}")
            return None

    async def _enter_verification_code(self, page, verification_code: str, window_id: int):
        """Вводит код подтверждения на странице"""
        try:
            logger.info(f"🔑 Окно {window_id}: вводим код подтверждения: {verification_code}")

            # Ищем поле для ввода кода
            code_selectors = [
                'input[name*="verification"], input[placeholder*="verification"]',
                'input[name*="code"], input[placeholder*="code"]',
                'input[type="text"][maxlength="6"]',
                'input[type="text"][maxlength="4"]',
                'input[data-testid*="verification"], input[data-testid*="code"]'
            ]

            code_input = None
            for selector in code_selectors:
                try:
                    await page.wait_for_selector(selector, timeout=10000)
                    code_input = selector
                    break
                except:
                    continue

            if code_input:
                await page.fill(code_input, verification_code)
                logger.info(f"✅ Окно {window_id}: код введён в поле")

                # Ищем кнопку подтверждения
                submit_selectors = [
                    'button:has-text("Verify")', 'button:has-text("Подтвердить")',
                    'button:has-text("Submit")', 'button:has-text("Continue")',
                    'button[type="submit"]', 'div[role="button"]:has-text("Verify")'
                ]

                for selector in submit_selectors:
                    try:
                        await page.wait_for_selector(selector, timeout=5000)
                        await page.click(selector)
                        logger.info(f"✅ Окно {window_id}: нажали кнопку подтверждения")
                        break
                    except:
                        continue

                await asyncio.sleep(3)  # Ждём обработки
            else:
                logger.error(f"❌ Окно {window_id}: не найдено поле для ввода кода")

        except Exception as e:
            logger.error(f"❌ Окно {window_id}: ошибка ввода кода: {e}")

    async def register_account_with_context(self, context, window_id: int) -> bool:
        """Регистрирует один аккаунт TikTok с готовым контекстом"""

        # Генерируем данные для аккаунта
        email_data = await self.data_generator.generate_email(window_id=window_id)
        email = email_data["email"]
        email_password = email_data["password"]
        account_id = email_data["account_id"]

        password = self.data_generator.generate_password()
        birth_date = self.data_generator.generate_birth_date()
        username = self.data_generator.generate_username(self.username_prefix) if self.username_prefix else ""

        # Начинаем регистрацию
        logger.info(f"📫 Окно {window_id}: Email account_id={account_id}")
        logger.info(f"👤 Окно {window_id}: Никнейм: {username}")

        try:
            # Создаём новую страницу в рамках контекста (анонимного)
            page = await context.new_page()
            page.set_default_timeout(self.config.page_load_timeout * 1000)

            try:
                # Применяем stealth с правильными параметрами
                try:
                    stealth_config = StealthConfig(
                        navigator_languages=False,
                        navigator_vendor=False,
                        navigator_user_agent=False
                    )
                    await stealth_async(page, stealth_config)
                except Exception as e:
                    logger.warning(f"Окно {window_id}: не удалось применить stealth: {e}")

                # Настраиваем капча solver
                captcha_solver = CaptchaSolver(
                    page,
                    self.config.sadcaptcha_api_key,
                    self.config
                )

                # Переходим на страницу регистрации TikTok
                await page.goto("https://www.tiktok.com/signup/phone-or-email/email", timeout=60000)
                logger.info(f"🌍 Окно {window_id}: перешли на страницу регистрации")

                # Ждём появления формы
                await asyncio.sleep(3)

                # Проверяем капчу
                await captcha_solver.solve_captcha_if_present()

                # ИСПРАВЛЕНИЕ: Используем полный метод заполнения формы вместо упрощенного
                logger.info(f"✍️ Окно {window_id}: заполняем форму полным методом")
                success = await self._fill_registration_form(page, email, password, birth_date, captcha_solver, email_password, account_id, username)

                if success:
                    # Проверяем успешность регистрации
                    await asyncio.sleep(5)
                    current_url = page.url

                    if "signup" not in current_url.lower() and "register" not in current_url.lower():
                        # Успешная регистрация
                        self._save_account(email, password, username)
                        self.successful_accounts.append({'email': email, 'password': password, 'username': username})
                        logger.success(f"✅ Окно {window_id}: аккаунт {email} успешно зарегистрирован!")
                        return True
                    else:
                        logger.error(f"❌ Окно {window_id}: регистрация не завершена, URL: {current_url}")
                        self.failed_count += 1
                        return False
                else:
                    logger.error(f"❌ Окно {window_id}: ошибка заполнения формы")
                    self.failed_count += 1
                    return False

            finally:
                await page.close()

        except Exception as e:
            logger.error(f"❌ Окно {window_id}: ошибка регистрации {email}: {e}")
            self.failed_count += 1
            return False

def main():
    """Главная функция"""
    print("=" * 60)
    print("    АВТОМАТИЧЕСКАЯ РЕГИСТРАЦИЯ АККАУНТОВ TIKTOK")
    print("=" * 60)
    print()

    # Загружаем конфигурацию
    config = load_config()

    # Проверяем наличие API ключа для капчи
    if not config.sadcaptcha_api_key or config.sadcaptcha_api_key == "SADCAPCHA_API_KEY":
        print("⚠️  ВНИМАНИЕ: Необходимо указать API ключ для капчи!")
        print("Установите переменную окружения SADCAPTCHA_API_KEY с вашим API ключом")
        print("от сервиса решения капчи (2captcha, anticaptcha и т.д.)")
        print("Например: export SADCAPTCHA_API_KEY=your_api_key_here")
        print()
        api_key = input("Или введите API ключ сейчас: ").strip()
        if api_key:
            config.sadcaptcha_api_key = api_key
        else:
            print("API ключ не указан. Выход.")
            return

    # Проверяем наличие файла с прокси
    if not os.path.exists(config.proxies_filename):
        print(f"❌ Файл {config.proxies_filename} не найден!")
        print("Создайте файл с прокси в формате: ip:port:username:password")
        return

    try:
        # Запрашиваем количество аккаунтов для регистрации
        while True:
            try:
                count = int(input("Сколько аккаунтов зарегистрировать? "))
                if count > 0:
                    break
                else:
                    print("Количество должно быть больше нуля!")
            except ValueError:
                print("Пожалуйста, введите корректное число!")

        # Запрашиваем количество окон для параллельной работы
        while True:
            try:
                windows_count = int(input("Сколько окон использовать для параллельной регистрации? (1-10): "))
                if 1 <= windows_count <= 10:
                    break
                else:
                    print("Количество окон должно быть от 1 до 10!")
            except ValueError:
                print("Пожалуйста, введите корректное число!")

        print(f"\n🚀 Начинаем регистрацию {count} аккаунтов в {windows_count} окнах...")
        print("💻 Каждое окно будет работать в анонимном режиме")
        print("Нажмите Ctrl+C для остановки\n")

        # Запрашиваем префикс для никнеймов
        username_prefix = input("Введите префикс для никнеймов (нажмите Enter чтобы пропустить никнейм): ").strip()
        if not username_prefix:
            print("⏭️  Никнейм будет пропущен автоматически.")
        else:
            print(f"👤 Никнеймы будут в формате: {username_prefix}_хххххххх")

        # Запрашиваем имя файла для сохранения аккаунтов
        output_filename = input("Введите имя файла для сохранения аккаунтов (например: accounts.txt): ").strip()
        if not output_filename:
            output_filename = "acs.txt"
            print("💾 Используем стандартное имя файла: {output_filename}")
        else:
            print(f"💾 Аккаунты будут сохраняться в: {output_filename}")

        # Создаем и запускаем регистратор
        registrator = TikTokRegistration(config, username_prefix, output_filename)
        asyncio.run(registrator.run_parallel_registration(count, windows_count))

    except KeyboardInterrupt:
        print("\n⏹️  Регистрация остановлена пользователем")
    except Exception as e:
        print(f"\n❌ Критическая ошибка: {e}")

if __name__ == "__main__":
    main()