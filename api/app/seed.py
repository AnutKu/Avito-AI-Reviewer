"""Демо-данные кабинета.

Сев идемпотентен и работает как «досоздать недостающее»: людей, задания и
работы он заводит по одному разу, опознавая их по устойчивому ключу — e-mail
для человека, название для задания. Поэтому кабинет, поднятый месяц назад,
получает новые задания и новых студентов при следующем старте, ничего не теряя
из уже накопленного.

Люди и работы адресуются по e-mail, а не по номеру в списке. Раньше «студент
номер 2» означал второго по алфавиту, и добавление одного человека тихо
переставляло всем оценки, просрочки и пропуски: данные оставались правдоподобными,
но переставали быть теми, что задумывались.
"""

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import (
    AiStatus,
    Assignment,
    BlitzSession,
    BlitzStatus,
    Confidence,
    Course,
    Enrollment,
    Notification,
    Review,
    ReviewAssignment,
    ReviewerAction,
    ReviewItem,
    Role,
    RubricVersion,
    Snapshot,
    StatusHistory,
    Submission,
    SubmissionStatus,
    User,
    Verdict,
)
from .services import late_penalty
from .services.mock_review import demo_blitz_questions, fill_demo_review

COURSE_TITLE = "Аналитика данных: поток 2026"

METHODIST = ("methodist@demo.local", "Анна Воронова")

REVIEWERS = (
    ("reviewer@demo.local", "Максим Орлов"),
    ("reviewer2@demo.local", "Елена Соколова"),
    ("reviewer3@demo.local", "Игорь Ефремов"),
    ("reviewer4@demo.local", "Наталья Белова"),
)

# Базовая «сила» студента: доля максимума, вокруг которой колеблются его баллы.
# Разброс нужен не для красоты — на одинаково сильной группе успеваемость
# выглядит плоской, а образовательный долг не находит ничего.
STUDENTS = (
    ("student@demo.local", "Алексей Смирнов", 0.92),
    ("student2@demo.local", "Мария Иванова", 0.80),
    ("student3@demo.local", "Дмитрий Волков", 0.66),
    ("student4@demo.local", "София Лебедева", 0.86),
    ("student5@demo.local", "Кирилл Попов", 0.74),
    ("student6@demo.local", "Алина Морозова", 0.90),
    ("student7@demo.local", "Егор Никитин", 0.70),
    ("student8@demo.local", "Полина Зайцева", 0.83),
    ("student9@demo.local", "Артём Ковалёв", 0.58),
    ("student10@demo.local", "Варвара Гусева", 0.88),
    ("student11@demo.local", "Никита Соловьёв", 0.77),
    ("student12@demo.local", "Ксения Романова", 0.72),
)

ALL_STUDENTS = tuple(email for email, _, _ in STUDENTS)
QUALITY = {email: quality for email, _, quality in STUDENTS}
# Порядковый номер студента в потоке. Нужен только затем, чтобы правки ревьюера
# и назначения не были одинаковыми у всех, но оставались воспроизводимыми.
ORDINAL = {email: index for index, (email, _, _) in enumerate(STUDENTS)}

# --------------------------------------------------------------------------- #
# Архив сданных ДЗ
#
# Дашборд, успеваемость и образовательный долг считаются по живым записям,
# поэтому одного текущего задания им мало: без закрытых работ нет ни динамики по
# неделям, ни статистики правок, ни среднего балла. Ниже — прошлые ДЗ курса.
#
# `drift` смещает баллы всей группы по заданию, `problem_index` называет
# критерий, вокруг которого ревьюер спорит с AI. Это и делает демо-курс
# небезупречным: на ровных данных разделу «образовательный долг» нечего сказать,
# а он ровно про то, где курс проседает.
# --------------------------------------------------------------------------- #

HISTORY_ASSIGNMENTS = (
    {
        "title": "Основы SQL: выборки и агрегаты",
        "topic": "SQL и витрины данных",
        "statement": (
            "Соберите отчёт по продажам за квартал: выберите нужные поля, соедините "
            "таблицы заказов и товаров, посчитайте агрегаты по категориям и оформите "
            "результат одним запросом."
        ),
        # Самое старое задание курса. Рубрику с тех пор не трогали, а работы по
        # нему идут — это и есть «задание отстало от программы» в разборе долга.
        "weeks_ago": 22,
        "effort_weight": 0.8,
        "pass_score": 6.0,
        "criteria": (
            ("sql_select", "Выборка и фильтрация", 2.0),
            ("sql_join", "Соединение таблиц", 3.0),
            ("sql_aggregate", "Агрегаты и группировки", 3.0),
            ("sql_style", "Читаемость запроса", 2.0),
        ),
        "weak_index": 1,
        "problem_index": None,
        "drift": -0.04,
        "assign_delay_hours": 24,
        "review_hours": 40.0,
        "skipped": ("student9@demo.local",),
        "overdue": ("student3@demo.local", "student12@demo.local"),
        "blitz": (),
    },
    {
        "title": "Проверка статистических гипотез",
        "topic": "Статистика и эксперименты",
        "statement": (
            "По данным о поведении пользователей сформулируйте гипотезу, выберите "
            "критерий проверки и обоснуйте его применимость, посчитайте p-value и "
            "сформулируйте вывод в терминах продукта, а не статистики."
        ),
        # Тема, на которой поток сыплется. Отрицательный сдвиг здесь не для
        # драматизма: без него в кабинете не на чем показать, как выглядит
        # «тему массово не поняли», и раздел долга остаётся пустым.
        "weeks_ago": 14,
        "effort_weight": 1.2,
        "pass_score": 6.0,
        "criteria": (
            ("hypothesis", "Формулировка гипотезы", 2.0),
            ("test_choice", "Выбор критерия и его применимость", 3.0),
            ("calculation", "Расчёт и интерпретация p-value", 3.0),
            ("business_conclusion", "Вывод для продукта", 2.0),
        ),
        "weak_index": 2,
        "problem_index": 1,
        "drift": -0.24,
        "assign_delay_hours": 16,
        "review_hours": 30.0,
        "skipped": ("student12@demo.local",),
        "overdue": ("student5@demo.local", "student9@demo.local"),
        "blitz": ("student3@demo.local", "student9@demo.local", "student7@demo.local"),
    },
    {
        "title": "Дизайн и анализ A/B-теста",
        "topic": "Статистика и эксперименты",
        "statement": (
            "Спроектируйте A/B-тест под продуктовую гипотезу: подберите метрику, "
            "оцените размер выборки и длительность, разберите результаты и скажите, "
            "можно ли раскатывать изменение."
        ),
        "weeks_ago": 11,
        "effort_weight": 1.3,
        "pass_score": 6.0,
        "criteria": (
            ("metric_choice", "Выбор метрики", 2.0),
            ("sample_size", "Размер выборки и длительность", 3.0),
            ("ab_analysis", "Анализ результатов", 3.0),
            ("rollout_decision", "Решение о раскатке", 2.0),
        ),
        "weak_index": None,
        "problem_index": 1,
        "drift": -0.19,
        "assign_delay_hours": 14,
        "review_hours": 28.0,
        "skipped": ("student7@demo.local",),
        "overdue": ("student2@demo.local",),
        "blitz": ("student5@demo.local", "student9@demo.local", "student12@demo.local", "student3@demo.local"),
    },
    {
        "title": "Дашборд и отчётность для продуктовой команды",
        "topic": "Визуализация и отчётность",
        "statement": (
            "Соберите дашборд по воронке продукта: выберите показатели, объясните "
            "выбор разрезов и подготовьте короткое сопровождение к цифрам для команды."
        ),
        "weeks_ago": 8,
        "effort_weight": 1.0,
        "pass_score": 6.0,
        "criteria": (
            ("dash_metrics", "Отбор показателей", 3.0),
            ("dash_layout", "Структура и разрезы", 2.0),
            ("dash_readability", "Читаемость визуализаций", 2.0),
            ("dash_story", "Сопровождение к цифрам", 3.0),
        ),
        "weak_index": None,
        "problem_index": None,
        "drift": -0.06,
        "assign_delay_hours": 18,
        "review_hours": 24.0,
        "skipped": ("student3@demo.local", "student11@demo.local"),
        "overdue": ("student9@demo.local",),
        "blitz": ("student9@demo.local",),
    },
    {
        "title": "Разведочный анализ данных",
        "topic": "Работа с данными",
        "statement": (
            "Изучите датасет: проверьте пропуски и выбросы, постройте распределения "
            "ключевых признаков и их взаимосвязи, сформулируйте гипотезы о том, что "
            "влияет на целевую переменную."
        ),
        "weeks_ago": 4,
        "effort_weight": 1.0,
        "pass_score": 6.0,
        "criteria": (
            ("data_quality", "Проверка качества данных", 3.0),
            ("visual_analysis", "Визуальный анализ признаков", 3.0),
            ("hypotheses", "Гипотезы и выводы", 2.0),
            ("notebook_style", "Оформление ноутбука", 2.0),
        ),
        "weak_index": None,
        "problem_index": None,
        "drift": -0.05,
        "assign_delay_hours": 20,
        "review_hours": 34.0,
        "skipped": (),
        "overdue": ("student2@demo.local", "student9@demo.local"),
        "blitz": ("student9@demo.local",),
    },
    {
        "title": "Базовая модель и метрики качества",
        "topic": "Модели и метрики",
        "statement": (
            "Обучите базовую модель, обоснуйте выбор метрик под задачу, опишите схему "
            "валидации и разберите типичные ошибки модели на примерах."
        ),
        "weeks_ago": 3,
        "effort_weight": 1.5,
        "pass_score": 6.0,
        "criteria": (
            ("baseline", "Обучение базовой модели", 3.0),
            ("metrics", "Выбор и обоснование метрик", 3.0),
            ("validation", "Схема валидации", 2.0),
            ("error_analysis", "Анализ ошибок", 2.0),
        ),
        "weak_index": None,
        "problem_index": None,
        "drift": 0.0,
        "assign_delay_hours": 12,
        "review_hours": 26.0,
        "skipped": ("student3@demo.local",),
        "overdue": ("student4@demo.local", "student7@demo.local"),
        "blitz": (),
    },
    {
        "title": "Отбор и конструирование признаков",
        "topic": "Работа с данными",
        "statement": (
            "Постройте новые признаки на основе доменных гипотез, оцените их вклад в "
            "качество модели и обоснуйте итоговый набор."
        ),
        "weeks_ago": 2,
        "effort_weight": 1.0,
        "pass_score": 6.0,
        "criteria": (
            ("feature_ideas", "Гипотезы о признаках", 2.0),
            ("feature_code", "Реализация преобразований", 3.0),
            ("feature_impact", "Оценка вклада признаков", 3.0),
            ("feature_selection", "Обоснование итогового набора", 2.0),
        ),
        "weak_index": None,
        "problem_index": 2,
        "drift": 0.02,
        "assign_delay_hours": 9,
        "review_hours": 20.0,
        "skipped": ("student2@demo.local", "student10@demo.local"),
        "overdue": ("student@demo.local",),
        "blitz": (),
    },
    {
        "title": "Подбор гиперпараметров",
        "topic": "Модели и метрики",
        "statement": (
            "Определите пространство поиска, подберите гиперпараметры выбранным методом, "
            "покажите контроль переобучения и зафиксируйте итоговую конфигурацию."
        ),
        "weeks_ago": 1,
        "effort_weight": 1.0,
        "pass_score": 6.0,
        "criteria": (
            ("search_space", "Пространство поиска", 2.0),
            ("search_method", "Метод подбора", 3.0),
            ("overfit_control", "Контроль переобучения", 3.0),
            ("conclusions", "Выводы и итоговая конфигурация", 2.0),
        ),
        "weak_index": None,
        "problem_index": None,
        "drift": 0.05,
        "assign_delay_hours": 6,
        "review_hours": 14.0,
        "skipped": ("student3@demo.local",),
        "overdue": ("student6@demo.local", "student11@demo.local"),
        "blitz": ("student9@demo.local",),
    },
)

# --------------------------------------------------------------------------- #
# Задания в работе
#
# Здесь курс живёт прямо сейчас: очередь ревьюера, распределение и «Успеваемость»
# показывают именно эти работы. Поэтому у трёх заданий разные фазы — только что
# выданное, идущее полным ходом и с уже прошедшим сроком: на одной фазе половина
# экранов кабинета пустует.
#
# `works` перечисляет, кто сдал и в каком состоянии работа. Кто в списке не
# назван — просто ещё не сдал, и это нормальная для курса картина.
# --------------------------------------------------------------------------- #

_S = SubmissionStatus

LIVE_ASSIGNMENTS = (
    {
        "title": "Трекинг экспериментов в MLflow",
        "topic": "Инструменты ML-инженера",
        "statement": (
            "Проведите серию экспериментов над моделью, зафиксируйте параметры и метрики "
            "в MLflow, сравните результаты и зарегистрируйте лучшую модель. Передайте ссылку "
            "на GitHub-репозиторий с воспроизводимым ноутбуком."
        ),
        "days_to_deadline": 2,
        "published_days_ago": 7,
        "effort_weight": 1.0,
        "pass_score": 6.0,
        "rubric_version": 3,
        "note": "Уточнены требования к Model Registry и воспроизводимости",
        "late_penalty": None,
        "source_slug": "mlflow-homework",
        # Разбор по этому заданию берётся из готовой фикстуры: её текст написан
        # именно про MLflow и совпадает с критериями ниже.
        "fixture": True,
        # Градация внутри критерия: за что ставится каждый балл. Её видит
        # ревьюер и AI-разбор, студент — нет. Уровни здесь целочисленные:
        # рубрика на 10 баллов из пяти критериев, дробить дальше нечего.
        "criteria": [
            {
                "key": "experiment_tracking",
                "title": "Трекинг экспериментов",
                "max_score": 3,
                "levels": [
                    {"points": 0, "label": "нет", "descriptor": "запуски не логируются или логируется только финальный прогон"},
                    {"points": 1, "label": "частично", "descriptor": "логируются метрики без параметров (или наоборот) — сравнить запуски нельзя"},
                    {"points": 2, "label": "почти полно", "descriptor": "параметры и метрики логируются, но часть прогонов заведена вручную или вне эксперимента"},
                    {"points": 3, "label": "полно", "descriptor": "у каждого прогона есть параметры, метрики и тег версии кода — запуски сравнимы между собой"},
                ],
            },
            {
                "key": "runs_count",
                "title": "Не менее 20 запусков",
                "max_score": 2,
                "levels": [
                    {"points": 0, "label": "нет", "descriptor": "меньше 10 запусков"},
                    {"points": 1, "label": "частично", "descriptor": "10–19 запусков либо запуски отличаются только сидом"},
                    {"points": 2, "label": "выполнено", "descriptor": "20 и больше запусков с разными гиперпараметрами"},
                ],
            },
            {
                "key": "model_registry",
                "title": "Регистрация лучшей модели",
                "max_score": 2,
                "levels": [
                    {"points": 0, "label": "нет", "descriptor": "модель в Model Registry не зарегистрирована"},
                    {"points": 1, "label": "частично", "descriptor": "модель зарегистрирована, но не видно, по какой метрике она выбрана лучшей"},
                    {"points": 2, "label": "выполнено", "descriptor": "зарегистрирована модель конкретного run_id, выбор обоснован метрикой"},
                ],
            },
            {
                "key": "reproducibility",
                "title": "Воспроизводимость",
                "max_score": 2,
                "levels": [
                    {"points": 0, "label": "нет", "descriptor": "сид не зафиксирован, версии библиотек не указаны — повторить прогон нельзя"},
                    {"points": 1, "label": "частично", "descriptor": "зафиксировано что-то одно: сид без версий или версии без сида"},
                    {"points": 2, "label": "выполнено", "descriptor": "сид зафиксирован, версии зафиксированы, ноутбук проходит сверху вниз"},
                ],
            },
            {
                "key": "conclusions",
                "title": "Выводы по экспериментам",
                "max_score": 1,
                "levels": [
                    {"points": 0, "label": "нет", "descriptor": "выводов нет или это пересказ таблицы метрик"},
                    {"points": 1, "label": "есть", "descriptor": "сказано, какой фактор на что повлиял, со ссылкой на конкретные прогоны"},
                ],
            },
        ],
        "works": (
            ("student@demo.local", _S.COMPLETED, 1.0, False),
            ("student2@demo.local", _S.IN_REVIEW, 0.82, False),
            ("student3@demo.local", _S.ASSIGNED, 0.68, False),
            ("student4@demo.local", _S.BLITZ_SENT, 0.9, False),
            ("student5@demo.local", _S.PROPOSED, 0.58, False),
            ("student6@demo.local", _S.SUBMITTED, 0.75, False),
            ("student7@demo.local", _S.IN_REVIEW, 0.63, False),
            ("student8@demo.local", _S.COMPLETED, 0.86, False),
            ("student10@demo.local", _S.ASSIGNED, 0.88, False),
            ("student11@demo.local", _S.SUBMITTED, 0.7, False),
        ),
    },
    {
        "title": "Витрина метрик для команды роста",
        "topic": "SQL и витрины данных",
        "statement": (
            "Соберите витрину ключевых метрик роста: опишите источники и гранулярность, "
            "напишите запрос сборки, заложите проверки качества данных и объясните, как "
            "витрину поддерживать при изменении источников.\n\n"
            "**Срок жёсткий:** за каждый день просрочки снимается 10% от максимального "
            "балла, но не больше 30% суммарно."
        ),
        # Срок уже прошёл — на этом задании видно, как считается штраф и как
        # ревьюер может его не применить.
        "days_to_deadline": -1,
        "published_days_ago": 12,
        "effort_weight": 1.2,
        "pass_score": 6.0,
        "rubric_version": 2,
        "note": "Добавлены проверки качества данных",
        "late_penalty": {"per_day": 10, "unit": "percent", "max_penalty": 30},
        "source_slug": "growth-metrics-mart",
        "fixture": False,
        "criteria": [
            {
                "key": "mart_sources",
                "title": "Источники и гранулярность",
                "max_score": 2,
                "levels": [
                    {"points": 0, "label": "нет", "descriptor": "источники не названы, единица строки витрины неясна"},
                    {"points": 1, "label": "частично", "descriptor": "источники перечислены, но гранулярность не зафиксирована"},
                    {"points": 2, "label": "выполнено", "descriptor": "названы источники и сказано, что означает одна строка витрины"},
                ],
            },
            {
                "key": "mart_query",
                "title": "Запрос сборки",
                "max_score": 3,
                "levels": [
                    {"points": 0, "label": "нет", "descriptor": "запрос не собирается или считает не то"},
                    {"points": 1, "label": "частично", "descriptor": "запрос работает, но дублирует строки на соединениях"},
                    {"points": 2, "label": "почти полно", "descriptor": "результат верный, но запрос нечитаем и не разбит на шаги"},
                    {"points": 3, "label": "полно", "descriptor": "результат верный, запрос разбит на понятные шаги"},
                ],
            },
            {
                "key": "mart_quality",
                "title": "Проверки качества данных",
                "max_score": 3,
                "levels": [
                    {"points": 0, "label": "нет", "descriptor": "проверок нет"},
                    {"points": 1, "label": "частично", "descriptor": "проверяются только пропуски"},
                    {"points": 2, "label": "почти полно", "descriptor": "есть проверки на пропуски и дубли"},
                    {"points": 3, "label": "полно", "descriptor": "проверяются пропуски, дубли и сходимость с источником"},
                ],
            },
            {
                "key": "mart_support",
                "title": "Поддержка при изменении источников",
                "max_score": 2,
                "levels": [
                    {"points": 0, "label": "нет", "descriptor": "вопрос не рассмотрен"},
                    {"points": 1, "label": "частично", "descriptor": "сказано в общих словах, без конкретного сценария"},
                    {"points": 2, "label": "выполнено", "descriptor": "разобран конкретный сценарий изменения схемы источника"},
                ],
            },
        ],
        "works": (
            ("student@demo.local", _S.COMPLETED, 0.94, False),
            ("student2@demo.local", _S.COMPLETED, 0.72, True),
            ("student3@demo.local", _S.IN_REVIEW, 0.5, True),
            ("student4@demo.local", _S.BLITZ_SENT, 0.8, False),
            ("student6@demo.local", _S.IN_REVIEW, 0.85, False),
            ("student7@demo.local", _S.ASSIGNED, 0.6, True),
            ("student8@demo.local", _S.COMPLETED, 0.77, False),
            ("student9@demo.local", _S.PROPOSED, 0.44, True),
            ("student10@demo.local", _S.ASSIGNED, 0.83, False),
            ("student11@demo.local", _S.SUBMITTED, 0.69, False),
        ),
    },
    {
        "title": "Прогноз оттока клиентов: сквозной пайплайн",
        "topic": "Модели и метрики",
        "statement": (
            "Соберите пайплайн от сырых данных до прогноза: подготовка признаков, "
            "обучение, валидация на отложенном периоде и оценка бизнес-эффекта. "
            "Пайплайн должен запускаться одной командой."
        ),
        # Только что выдано: сдали единицы, часть работ ещё ждёт распределения —
        # на этом задании видно, чем занят экран «Распределение ревьюеров».
        "days_to_deadline": 9,
        "published_days_ago": 2,
        "effort_weight": 1.5,
        "pass_score": 6.0,
        "rubric_version": 1,
        "note": "Первая версия",
        "late_penalty": {"per_day": 0.5, "unit": "points", "max_penalty": 2},
        "source_slug": "churn-pipeline",
        "fixture": False,
        "criteria": [
            {"key": "pipe_features", "title": "Подготовка признаков", "max_score": 3},
            {"key": "pipe_training", "title": "Обучение модели", "max_score": 2},
            {"key": "pipe_validation", "title": "Валидация на отложенном периоде", "max_score": 3},
            {"key": "pipe_impact", "title": "Оценка бизнес-эффекта", "max_score": 2},
        ],
        "works": (
            ("student@demo.local", _S.PROPOSED, 0.9, False),
            ("student4@demo.local", _S.SUBMITTED, 0.81, False),
            ("student8@demo.local", _S.ASSIGNED, 0.76, False),
            ("student10@demo.local", _S.SUBMITTED, 0.87, False),
        ),
    },
)


# --------------------------------------------------------------------------- #
#  Сборка
# --------------------------------------------------------------------------- #


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _verdict(score: float, max_score: float) -> str:
    if score >= max_score * 0.85:
        return Verdict.PASSED
    if score <= max_score * 0.35:
        return Verdict.FAILED
    return Verdict.PARTIAL


def _decision(spec: dict, ordinal: int, position: int, score: float, max_score: float):
    """Решение ревьюера по критерию: (действие, итоговый балл).

    Правки не размазаны равномерно — иначе «критерии с частыми правками»
    показывали бы одинаковый шум по всем строкам. У части заданий есть спорный
    критерий (`problem_index`), вокруг которого ревьюер расходится с AI примерно
    на половине работ; у остальных заданий спорного критерия нет вовсе, и разбор
    долга не обязан находить проблему в каждой рубрике курса."""

    problem = spec["problem_index"]
    if problem is not None and position == problem:
        # Половина работ проходит как есть: спор ревьюера с моделью — это
        # заметная доля, а не приговор критерию.
        if ordinal % 2 == 0:
            return ReviewerAction.ACCEPTED, score
        if ordinal % 5 == 3:
            return ReviewerAction.REJECTED, None
        step = 0.5 if ordinal % 3 == 0 else -0.5
        return ReviewerAction.CHANGED, _clamp(score + step, 0.0, max_score)
    # Соседний критерий изредка подправляют — фон, который не должен
    # дотягивать до порога находки.
    neighbour = 0 if problem is None else (problem + 1) % len(spec["criteria"])
    if position == neighbour and ordinal % 3 == 0:
        return ReviewerAction.CHANGED, _clamp(score - 0.5, 0.0, max_score)
    return ReviewerAction.ACCEPTED, score


def _ai_items(
    db: Session,
    review: Review,
    criteria: list[dict],
    quality: float,
    drift: float,
    ordinal: int,
    weak: int | None = None,
):
    """Разбор AI по критериям рубрики.

    Баллы разъезжаются вокруг «силы» студента, а не совпадают с ней: одинаковая
    оценка по всем критериям выглядит как заглушка и не даёт аналитике ничего,
    кроме среднего."""

    items = []
    for position, criterion in enumerate(criteria):
        max_score = criterion["max_score"]
        value = _clamp(
            quality + drift + ((ordinal + position) % 3 - 1) * 0.06
            # Требование, которое не даётся почти никому: обычно это не «тема
            # сложная», а невнятная формулировка в условии — ровно то, что
            # разбор долга должен уметь показывать отдельно от темы.
            - (0.22 if position == weak else 0.0)
        )
        ai_score = round(max_score * value * 2) / 2
        items.append(
            ReviewItem(
                review=review,
                position=position,
                criterion_key=criterion["key"],
                criterion_title=criterion["title"],
                max_score=max_score,
                ai_score=ai_score,
                verdict=_verdict(ai_score, max_score),
                confidence=Confidence.MEDIUM,
                evidence=[{"quote": "Фрагмент работы", "anchor": f"Ячейка {position + 3}"}],
                recommendation=f"Замечание по критерию «{criterion['title']}».",
            )
        )
    # Явное добавление в сессию обязательно: с SQLAlchemy 2.0 связь
    # `review=review` сама объект в сессию не тянет, и без этой строки разбор
    # молча не сохранялся — ревью было, а критериев в нём не было.
    db.add_all(items)
    return items


def _ensure_assignment(
    db: Session,
    *,
    course: Course,
    title: str,
    criteria: list[dict],
    fields: dict,
    rubric_fields: dict,
) -> tuple[Assignment, RubricVersion, bool]:
    """Задание с рубрикой. Уже заведённое возвращается как есть.

    Опознаётся по названию внутри курса: другого устойчивого ключа у задания
    нет, а перезаписывать чужие правки сев не имеет права — методист мог
    отредактировать демо-задание, и это его текст, а не наш."""

    assignment = db.scalar(
        select(Assignment).where(Assignment.course_id == course.id, Assignment.title == title)
    )
    if assignment:
        rubric = db.scalar(
            select(RubricVersion)
            .where(RubricVersion.assignment_id == assignment.id)
            .order_by(RubricVersion.version.desc())
        )
        return assignment, rubric, False

    assignment = Assignment(course_id=course.id, title=title, **fields)
    db.add(assignment)
    db.flush()
    rubric = RubricVersion(
        assignment_id=assignment.id,
        criteria=criteria,
        max_score=sum(item["max_score"] for item in criteria),
        **rubric_fields,
    )
    db.add(rubric)
    db.flush()
    assignment.current_rubric_version_id = rubric.id
    return assignment, rubric, True


def _pending_students(db: Session, assignment: Assignment, roster: list[str], students: dict) -> list[str]:
    """Кто из списка ещё не сдавал это задание.

    Досев работ по одному студенту — то, ради чего он вообще идемпотентен: поток
    пополняется, и новичок без архива смотрелся бы в журнале пустой строкой."""

    done = set(
        db.scalars(select(Submission.student_id).where(Submission.assignment_id == assignment.id))
    )
    return [email for email in roster if email in students and students[email].id not in done]


def _archived_answers(questions: list[dict]) -> list[dict]:
    return [
        {"question_id": question["id"], "text": "Ответ студента из архива демо-курса."}
        for question in questions
    ]


def _seed_history_assignment(
    db: Session,
    spec: dict,
    *,
    course: Course,
    methodist: User | None,
    reviewers: list[User],
    students: dict[str, User],
    now: datetime,
) -> bool:
    deadline = now - timedelta(weeks=spec["weeks_ago"])
    opened = deadline - timedelta(days=10)
    assignment, rubric, _ = _ensure_assignment(
        db,
        course=course,
        title=spec["title"],
        criteria=[
            {"key": key, "title": title, "max_score": max_score}
            for key, title, max_score in spec["criteria"]
        ],
        fields=dict(
            statement=spec["statement"],
            deadline_at=deadline,
            effort_weight=spec["effort_weight"],
            submission_channel="github",
            # Тема нужна разбору образовательного долга: он группирует работы по
            # ней, чтобы отличить «не понимают эту тему» от «сложное задание».
            authoring={"topic": spec["topic"]},
            published_at=opened,
            created_at=opened,
        ),
        rubric_fields=dict(
            version=1,
            pass_score=spec["pass_score"],
            author_id=methodist.id if methodist else None,
            published_at=opened,
            note="Архивная версия задания",
        ),
    )

    roster = [email for email in ALL_STUDENTS if email not in spec["skipped"]]
    todo = _pending_students(db, assignment, roster, students)
    if not todo:
        return False

    criteria = rubric.criteria
    slug = spec["criteria"][0][0]
    submitted = {}
    for email in todo:
        overdue = email in spec["overdue"]
        ordinal = ORDINAL[email]
        submission = Submission(
            assignment_id=assignment.id,
            student_id=students[email].id,
            source_url=f"https://github.com/demo-student/{slug}-{ordinal + 1}",
            submitted_at=(
                deadline + timedelta(hours=7)
                if overdue
                else deadline - timedelta(hours=8 + ordinal * 5)
            ),
            status=SubmissionStatus.COMPLETED,
            is_overdue=overdue,
        )
        db.add(submission)
        submitted[email] = submission
    db.flush()

    reviews = {}
    for email, submission in submitted.items():
        ordinal = ORDINAL[email]
        submitted_at = submission.submitted_at
        reviewer = reviewers[(ordinal + spec["weeks_ago"]) % len(reviewers)]
        approved_at = submitted_at + timedelta(hours=spec["assign_delay_hours"])
        completed_at = approved_at + timedelta(hours=spec["review_hours"] + ordinal * 1.5)
        db.add(
            Snapshot(
                submission_id=submission.id,
                content=f"# {spec['title']}\n\nАрхивная работа демо-курса.\n",
                content_hash=f"demo-{slug}-{ordinal + 1:02d}",
                fetched_at=submitted_at,
                parsed_facts={"archived": True, "seed": 42},
            )
        )
        db.add(
            ReviewAssignment(
                submission_id=submission.id,
                reviewer_id=reviewer.id,
                explanation="Специализация совпадает · минимальная загрузка на момент назначения",
                approved_by=methodist.id if methodist else None,
                approved_at=approved_at,
                created_at=submitted_at + timedelta(minutes=5),
            )
        )
        review = Review(
            submission_id=submission.id,
            rubric_version_id=rubric.id,
            model="demo-fixture/v1",
            ai_status=AiStatus.READY,
            raw_result={
                "summary": f"Архивное ревью по заданию «{spec['title']}».",
                "pipeline": ["extract", "grade", "signal", "feedback"],
                "demo_data": True,
            },
            draft_feedback="Черновик обратной связи из архива демо-курса.",
            final_feedback="Обратная связь опубликована ревьюером.",
            completed_by=reviewer.id,
            completed_at=completed_at,
            created_at=submitted_at + timedelta(minutes=2),
        )
        db.add(review)

        total = 0.0
        for position, item in enumerate(
            _ai_items(
                db, review, criteria, QUALITY[email], spec["drift"], ordinal, spec["weak_index"]
            )
        ):
            action, final_score = _decision(spec, ordinal, position, item.ai_score, item.max_score)
            item.reviewer_action = action
            item.final_score = final_score
            item.reviewer_comment = (
                "" if action == ReviewerAction.ACCEPTED else "Скорректировано ревьюером"
            )
            total += final_score or 0.0
        review.final_score = round(total, 1)
        reviews[email] = review

        db.add_all(
            [
                StatusHistory(
                    submission_id=submission.id,
                    from_status=None,
                    to_status=SubmissionStatus.SUBMITTED,
                    actor_id=students[email].id,
                    comment="Работа сдана",
                    created_at=submitted_at,
                ),
                StatusHistory(
                    submission_id=submission.id,
                    from_status=SubmissionStatus.IN_REVIEW,
                    to_status=SubmissionStatus.COMPLETED,
                    actor_id=reviewer.id,
                    comment="Проверка завершена",
                    created_at=completed_at,
                ),
            ]
        )
    db.flush()

    # Блиц по архивным работам: ревьюер переспрашивал и получил ответ. Разбор
    # образовательного долга считает по нему «задания, после которых приходится
    # уточнять» — без отправленных опросов сигнала просто нет.
    questions = demo_blitz_questions()
    for email in spec["blitz"]:
        review = reviews.get(email)
        if review is None:
            continue
        sent_at = review.completed_at - timedelta(hours=6)
        db.add(
            BlitzSession(
                review_id=review.id,
                status=BlitzStatus.ANSWERED,
                questions=questions,
                answers=_archived_answers(questions),
                sent_at=sent_at,
                due_at=sent_at + timedelta(hours=48),
                answered_at=sent_at + timedelta(hours=5),
                reviewer_decision="accepted",
            )
        )
    return True


def _seed_live_assignment(
    db: Session,
    spec: dict,
    *,
    course: Course,
    methodist: User | None,
    reviewers: list[User],
    students: dict[str, User],
    now: datetime,
) -> bool:
    deadline = now + timedelta(days=spec["days_to_deadline"])
    opened = now - timedelta(days=spec["published_days_ago"])
    authoring = {"topic": spec["topic"]}
    if spec["late_penalty"]:
        authoring["late_penalty"] = spec["late_penalty"]

    assignment, rubric, _ = _ensure_assignment(
        db,
        course=course,
        title=spec["title"],
        criteria=spec["criteria"],
        fields=dict(
            statement=spec["statement"],
            deadline_at=deadline,
            effort_weight=spec["effort_weight"],
            submission_channel="github",
            authoring=authoring,
            published_at=opened,
            created_at=opened,
        ),
        rubric_fields=dict(
            version=spec["rubric_version"],
            pass_score=spec["pass_score"],
            author_id=methodist.id if methodist else None,
            published_at=opened,
            note=spec["note"],
        ),
    )

    todo = set(_pending_students(db, assignment, [work[0] for work in spec["works"]], students))
    works = [work for work in spec["works"] if work[0] in todo]
    if not works:
        return False

    criteria = rubric.criteria
    rule = late_penalty.parse_rule(authoring.get("late_penalty"))
    pending = []
    for email, status, quality, late in works:
        ordinal = ORDINAL[email]
        # Опоздавший сдаёт после срока, остальные — до него. Раньше просрочка
        # была отдельным флагом и могла стоять на работе, сданной за два дня до
        # дедлайна: в кабинете это выглядело как ошибка расчёта.
        submitted_at = (
            deadline + timedelta(hours=6 + (ordinal % 4) * 9)
            if late
            else min(deadline, now) - timedelta(hours=6 + ordinal * 3)
        )
        submission = Submission(
            assignment_id=assignment.id,
            student_id=students[email].id,
            source_url=f"https://github.com/demo-student/{spec['source_slug']}-{ordinal + 1}",
            submitted_at=submitted_at,
            status=status,
            is_overdue=submitted_at > deadline,
        )
        db.add(submission)
        pending.append((email, status, quality, submission))
    db.flush()

    # Ревью заводятся отдельным проходом: готовой фикстуре нужен уже
    # существующий `review.id` — сигналы она привязывает по нему, а не через
    # связь, и до flush такой сигнал уходит в базу с пустой ссылкой.
    reviews = {}
    for email, _status, _quality, submission in pending:
        ordinal = ORDINAL[email]
        db.add(
            Snapshot(
                submission_id=submission.id,
                content=f"# {spec['title']}\n\nРабота студента, демо-курс.\n",
                content_hash=f"demo-{spec['source_slug']}-{ordinal + 1:02d}",
                fetched_at=submission.submitted_at,
                parsed_facts={"seed": 42},
            )
        )
        review = Review(submission_id=submission.id, rubric_version_id=rubric.id)
        db.add(review)
        reviews[email] = review
    db.flush()

    blitz_for = []
    for index, (email, status, quality, submission) in enumerate(pending):
        ordinal = ORDINAL[email]
        submitted_at = submission.submitted_at
        review = reviews[email]

        # Разбор существует только там, где ревьюер уже назначен. Работа,
        # ждущая распределения, приходила сюда с готовым «разбором», которого
        # никто не делал: методист её назначал, ревьюер открывал и видел чужой
        # придуманный текст под своей фамилией. Теперь такая работа лежит с
        # `pending`, и разбор по ней запускает назначение — как в проде.
        graded = status not in (SubmissionStatus.SUBMITTED, SubmissionStatus.PROPOSED)
        if graded and spec["fixture"]:
            fill_demo_review(db, review, quality)
        elif graded:
            review.ai_status = AiStatus.READY
            review.model = "demo-fixture/v1"
            review.raw_result = {
                "summary": f"Разбор по заданию «{spec['title']}».",
                "pipeline": ["extract", "grade", "signal", "feedback"],
                "demo_data": True,
            }
            review.draft_feedback = (
                "Черновик обратной связи: основная часть выполнена, часть критериев "
                "требует решения ревьюера."
            )
            _ai_items(db, review, criteria, quality, 0.0, ordinal)

        reviewer = reviewers[(ordinal + index) % len(reviewers)]
        if graded:
            db.add(
                ReviewAssignment(
                    submission_id=submission.id,
                    reviewer_id=reviewer.id,
                    explanation="Специализация совпадает · минимальная загрузка на момент назначения",
                    approved_by=methodist.id if methodist else None,
                    approved_at=submitted_at + timedelta(hours=4),
                    created_at=submitted_at + timedelta(minutes=5),
                )
            )
        if status == SubmissionStatus.PROPOSED:
            # Предложение балансировщика, которое методист ещё не подтвердил.
            db.add(
                ReviewAssignment(
                    submission_id=submission.id,
                    reviewer_id=reviewer.id,
                    explanation="Специализация совпадает · загрузка 2 работы · рассмотрено кандидатов: 2",
                    created_at=submitted_at + timedelta(minutes=5),
                )
            )
        if status == SubmissionStatus.COMPLETED:
            earned = 0.0
            for item in review.items:
                item.reviewer_action = ReviewerAction.ACCEPTED
                item.final_score = item.ai_score
                earned += item.ai_score
            days = late_penalty.late_days(deadline, submitted_at)
            fine = late_penalty.penalty(rule, days, score=earned, max_score=rubric.max_score)
            review.late_penalty = fine
            review.late_penalty_note = late_penalty.explain(rule, days, fine)
            review.final_score = round(earned - fine, 2)
            review.final_feedback = review.draft_feedback
            review.completed_by = reviewer.id
            review.completed_at = submitted_at + timedelta(hours=20)
        if status == SubmissionStatus.BLITZ_SENT:
            blitz_for.append((review, submitted_at))

        db.add(
            StatusHistory(
                submission_id=submission.id,
                from_status=None,
                to_status=status,
                actor_id=methodist.id if methodist else None,
                comment="Демонстрационная история",
                created_at=submitted_at,
            )
        )
    db.flush()

    for review, submitted_at in blitz_for:
        sent_at = submitted_at + timedelta(hours=6)
        db.add(
            BlitzSession(
                review_id=review.id,
                status=BlitzStatus.SENT,
                questions=demo_blitz_questions(),
                sent_at=sent_at,
                due_at=sent_at + timedelta(hours=48),
            )
        )
    return True


def _ensure_people(db: Session, course: Course) -> tuple[User, list[User], dict[str, User]]:
    """Люди курса. Ключ — e-mail: под ним же входят в демо-режиме.

    Досоздаёт недостающих, а не пересоздаёт всех: поток можно пополнить, не
    трогая уже накопленные работы и оценки."""

    known = {user.email: user for user in db.scalars(select(User))}

    def ensure(email: str, name: str, role: str, specialization: str | None = None) -> User:
        user = known.get(email)
        if user is None:
            user = User(email=email, full_name=name, role=role, specialization=specialization)
            db.add(user)
            known[email] = user
        return user

    methodist = ensure(METHODIST[0], METHODIST[1], Role.METHODIST, "data_science")
    reviewers = [ensure(email, name, Role.REVIEWER, "data_science") for email, name in REVIEWERS]
    students = {email: ensure(email, name, Role.STUDENT) for email, name, _ in STUDENTS}
    db.flush()

    enrolled = set(
        db.scalars(select(Enrollment.user_id).where(Enrollment.course_id == course.id))
    )
    for student in students.values():
        if student.id not in enrolled:
            db.add(Enrollment(course_id=course.id, user_id=student.id))
    db.flush()
    return methodist, reviewers, students


def _ensure_course(db: Session) -> Course:
    course = db.scalar(select(Course).order_by(Course.created_at))
    if course:
        return course
    course = Course(
        title=COURSE_TITLE,
        specialization="data_science",
        reviewer_capacity=12,
        tone_of_voice={
            "style": "доброжелательный и предметный",
            "address": "на вы",
            "rules": ["Начинать с сильных сторон", "Замечания подкреплять примером"],
        },
    )
    db.add(course)
    db.flush()
    return course


def _demo_notifications(methodist: User, reviewers: list[User], students: dict[str, User]):
    return [
        Notification(
            recipient_id=reviewers[0].id,
            kind="assignment",
            title="Назначены новые работы",
            body="В очереди 2 работы по MLflow",
            payload={"route": "/reviewer/queue"},
        ),
        Notification(
            recipient_id=methodist.id,
            kind="deadline_risk",
            title="Риск просрочки",
            body="Одна работа не начата менее чем за 24 часа до контрольного срока",
            payload={"route": "/methodist/performance"},
        ),
        Notification(
            recipient_id=students[ALL_STUDENTS[0]].id,
            kind="review_completed",
            title="Работа проверена",
            body="Опубликованы оценка и обратная связь",
            payload={"route": "/student/assignments"},
        ),
    ]


def seed_demo(db: Session) -> None:
    """Досеять демо-курс до полного состава. Безопасно вызывать на каждом старте."""

    legacy_reviews = list(db.scalars(select(Review).where(Review.model == "mock/ai-review-v1")))
    for review in legacy_reviews:
        review.model = "demo-fixture/v1"
        review.raw_result = {**review.raw_result, "mock": False, "demo_data": True}

    fresh = db.scalar(select(User.id).limit(1)) is None
    course = _ensure_course(db)
    methodist, reviewers, students = _ensure_people(db, course)
    now = datetime.now(UTC)

    people = dict(
        course=course, methodist=methodist, reviewers=reviewers, students=students, now=now
    )
    for spec in HISTORY_ASSIGNMENTS:
        _seed_history_assignment(db, spec, **people)
    for spec in LIVE_ASSIGNMENTS:
        _seed_live_assignment(db, spec, **people)

    if fresh:
        db.add_all(_demo_notifications(methodist, reviewers, students))
    db.commit()
