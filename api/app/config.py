from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://avito:avito@localhost:5432/avito_ai_reviewer"
    jwt_secret: str = "dev-secret-change-me"
    jwt_algorithm: str = "HS256"
    jwt_ttl_hours: int = 24
    seed_on_start: bool = True

    ai_reviewer_url: str = "http://localhost:8010"
    ai_reviewer_model: str = "glm-5.3-flash"
    ai_reviewer_timeout_seconds: float = 150.0
    zai_input_cost_per_million: float = 0.075
    zai_output_cost_per_million: float = 0.25

    # Фиче-флаги. Выключенный раздел не появляется в навигации — кабинет
    # всегда выглядит целым, порядок отказа применяется конфигом, не вырезкой кода.
    feature_distribution: bool = True
    feature_rubric_builder: bool = True
    feature_analytics: bool = True
    feature_blitz: bool = True
    feature_course_debt: bool = False
    feature_telegram: bool = False

    def feature_flags(self) -> dict[str, bool]:
        return {
            "distribution": self.feature_distribution,
            "rubric_builder": self.feature_rubric_builder,
            "analytics": self.feature_analytics,
            "blitz": self.feature_blitz,
            "course_debt": self.feature_course_debt,
            "telegram": self.feature_telegram,
        }


settings = Settings()

# Разделы, которые в прототипе стоят на фикстурах. Интерфейс обязан показывать
# на них бейдж «демо-данные» — см. §10 проектного решения.
DEMO_DATA_SECTIONS = ["analytics", "dashboard", "course_debt"]

# Пока модули AI-ревью и AI-конструктора не приехали, кабинет работает на моке
# в том же контракте, что и настоящий пайплайн.
MOCK_MODULES = ["rubric_ci", "blitz"]
