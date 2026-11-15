from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from .config import DATABASE_URL

# Создаем движок
engine = create_engine(DATABASE_URL, echo=False)

# Создаем фабрику сессий (autocommit=False, autoflush=False)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Базовый класс для моделей
Base = declarative_base()

# Функция-генератор для получения сессии (удобно для FastAPI/Streamlit)
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()