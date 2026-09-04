from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://avito:avito@localhost:5432/avito_ai_reviewer"
    jwt_secret: str = "dev-secret-change-me"
    jwt_algorithm: str = "HS256"
    jwt_ttl_hours: int = 24
    seed_on_start: bool = True

    # Кому браузер разрешает кросс-доменные запросы к API. "*" — любой источник:
    # кабинет и коллеги с других машин ходят каждый со своего Origin, и без
    # этого их запросы блокирует CORS. Список через запятую сужает до адресов.
    cors_allow_origins: str = "*"

    ai_reviewer_url: str = "http://localhost:8010"
    ai_reviewer_model: str = "glm-5.3-flash"
    ai_reviewer_timeout_seconds: float = 150.0
    zai_input_cost_per_million: float = 0.075
    zai_output_cost_per_million: float = 0.25

    # Потолок снапшота. Тот же MAX_SNAPSHOT_CHARS читает сервис ai-reviewer, поэтому
    # значение одно на оба контейнера: обрезать должен только тот, кто собирает
    # снапшот, а не молча второй раз тот, кто его отправляет в модель.
    max_snapshot_chars: int = 120_000

    # Ревью выполняется в BackgroundTasks того же процесса uvicorn: очереди нет.
    # Отсюда два свойства, которые нельзя оставлять на «как повезёт»:
    # повтор транзиентной ошибки провайдера и срок, после которого запись,
    # оставшуюся в running от умершего процесса, считаем мёртвой.
    ai_review_max_attempts: int = 2
    ai_review_retry_delay_seconds: float = 3.0
    ai_review_stale_after_seconds: float = 600.0

    # Конструктор заданий. Движок (микросервис task-creater) генерирует блоки и
    # гоняет AI-персон; хранит задание кабинет, поэтому наружу движок не торчит
    # и фронт в него не ходит. Прогон живёт в BackgroundTasks этого процесса —
    # отсюда те же два свойства, что у ревью: потолок ожидания и срок, после
    # которого запись, оставшуюся в running от умершего процесса, считаем мёртвой.
    taskcreater_url: str = "http://localhost:8082"
    # Заполнение блока — это живой вызов модели, да ещё и первый после старта
    # контейнера тянет за собой инициализацию шлюза. Тридцати секунд на это не
    # хватало, и пользователь видел «сервис недоступен» там, где надо подождать.
    taskcreater_timeout_seconds: float = 90.0
    ai_task_run_poll_seconds: float = 2.0
    ai_task_run_timeout_seconds: float = 900.0
    ai_task_run_stale_after_seconds: float = 1200.0

    # Детекция. Веса признаков лежат в services/detection_scale.py — здесь только
    # переопределения: калибровать шкалу приходится под курс, а пересобирать образ
    # ради одного числа не нужно. Порог, с которого интерфейс ПРЕДЛАГАЕТ блиц
    # (FR-047) — не порог санкции: балл от индекса не зависит никогда (FR-045).
    detection_weights: dict[str, float] = {}
    detection_blitz_threshold: int = 70

    # Фиче-флаги. Выключенный раздел не появляется в навигации — кабинет
    # всегда выглядит целым, порядок отказа применяется конфигом, не вырезкой кода.
    feature_distribution: bool = True
    feature_rubric_builder: bool = True
    feature_analytics: bool = True
    feature_blitz: bool = True
    feature_ai_detection: bool = True
    feature_course_debt: bool = False
    feature_telegram: bool = False

    def feature_flags(self) -> dict[str, bool]:
        return {
            "distribution": self.feature_distribution,
            "rubric_builder": self.feature_rubric_builder,
            "analytics": self.feature_analytics,
            "blitz": self.feature_blitz,
            "ai_detection": self.feature_ai_detection,
            "course_debt": self.feature_course_debt,
            "telegram": self.feature_telegram,
        }


settings = Settings()

# Разделы, которые в прототипе стоят на фикстурах. Интерфейс обязан показывать
# на них бейдж «демо-данные» — см. §10 проектного решения. Дашборд и аналитика
# из списка ушли: они считаются по живым записям, а сколько из них демо-фикстуры,
# экран показывает отдельной строкой (`demo_reviews` в ответе аналитики).
DEMO_DATA_SECTIONS = ["course_debt"]

# Пока модули не приехали, кабинет работает на моке в том же контракте, что и
# настоящий пайплайн. Блиц отсюда ушёл: вопросы генерирует модель по конкретному
# решению, ответы разбираются, поведение при ответе собирается.
MOCK_MODULES = ["rubric_ci"]
