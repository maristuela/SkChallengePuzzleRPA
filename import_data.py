import pandas as pd
from sqlalchemy import create_engine
import os

# --- НАСТРОЙКИ ---
DB_USER = "postgres"
DB_PASSWORD = "postgres"  # Тот пароль, который подошел в pgAdmin
DB_HOST = "localhost"
DB_PORT = "5432"
DB_NAME = "puzzle_bi"  # Имя базы, которую мы только что создали

# Укажите путь к папке с CSV файлами
DATA_DIR = r"C:\Users\Maria\Downloads\Sk students data\data"

engine = create_engine(f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}")

for filename in os.listdir(DATA_DIR):
    if filename.endswith(".csv"):
        table_name = filename.replace(".csv", "").lower()
        file_path = os.path.join(DATA_DIR, filename)

        print(f"Импортирую {filename} в таблицу {table_name}...")
        try:
            # Читаем CSV
            df = pd.read_csv(file_path, sep=',', encoding='utf-8')
            # Загружаем в базу
            df.to_sql(table_name, engine, if_exists='replace', index=False)
            print(f"  Успешно! Загружено строк: {len(df)}")
        except Exception as e:
            print(f"  Ошибка при импорте {filename}: {e}")

print("Импорт завершен!")