"""Точка входа в приложение."""
import sys
from pathlib import Path

# Добавляем корневую директорию проекта в путь
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from loguru import logger
from src.config.settings import Settings
from src.utils.logger import setup_logger
from src.parsers.wb_parser import WildberriesParser


def main() -> int:
    """Основная функция приложения.
    
    Returns:
        Код возврата (0 - успех, 1 - ошибка)
    """
    try:
        # Загрузка настроек
        settings = Settings()
        
        # Настройка логирования
        setup_logger(settings.logs_dir, debug=settings.debug)
        
        logger.info("=" * 60)
        logger.info("Запуск парсера цен Wildberries и Ozon")
        logger.info("=" * 60)
        
        # Получаем API ключи и ID кабинетов
        wb_api_keys = settings.get_wb_api_keys()
        wb_cabinet_ids = settings.get_wb_cabinet_ids()
        
        # Проверяем наличие API ключей
        missing_keys = [name for name, key in wb_api_keys.items() if not key]
        if missing_keys:
            logger.warning(f"Отсутствуют API ключи для кабинетов: {', '.join(missing_keys)}")
            logger.info("Продолжаем работу только с доступными кабинетами")
        
        # Обработка кабинетов WB
        all_results = []
        
        for cabinet_name, api_key in wb_api_keys.items():
            if not api_key:
                logger.warning(f"Пропускаем кабинет {cabinet_name} - нет API ключа")
                continue
            
            cabinet_id = wb_cabinet_ids.get(cabinet_name)
            if not cabinet_id:
                logger.warning(f"Пропускаем кабинет {cabinet_name} - нет ID кабинета")
                continue
            
            logger.info(f"Обработка кабинета: {cabinet_name} (ID: {cabinet_id})")
            
            try:
                parser = WildberriesParser(
                    api_key=api_key,
                    cabinet_name=cabinet_name,
                    cabinet_id=cabinet_id,
                    request_delay=settings.request_delay,
                )
                
                # Парсинг базовых цен (читает артикулы из Articles.xlsx)
                basic_prices = parser.parse_basic_prices()
                all_results.extend(basic_prices)
                
                logger.success(f"Кабинет {cabinet_name} обработан: {len(basic_prices)} товаров")
                
            except Exception as e:
                logger.error(f"Ошибка при обработке кабинета {cabinet_name}: {e}")
                logger.exception("Детали ошибки:")
                continue
        
        logger.info("=" * 60)
        logger.success(f"Обработка завершена. Всего товаров: {len(all_results)}")
        logger.info("=" * 60)
        
        # Экспорт результатов
        if all_results:
            try:
                import pandas as pd
                from datetime import datetime
                
                # Создаём DataFrame
                df = pd.DataFrame(all_results)
                
                # Сортируем по кабинету и артикулу для удобства
                if 'cabinet' in df.columns and 'vendor_code' in df.columns:
                    df = df.sort_values(['cabinet', 'vendor_code', 'size_name'], ascending=[True, True, True])
                
                # Формируем имя файла с датой и временем
                timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
                output_file = settings.output_dir / f"wb_prices_{timestamp}.xlsx"
                
                # Сохраняем в Excel с форматированием
                with pd.ExcelWriter(output_file, engine='openpyxl') as writer:
                    df.to_excel(writer, index=False, sheet_name='Prices')
                    
                    # Получаем worksheet для форматирования
                    worksheet = writer.sheets['Prices']
                    
                    # Автоматически подгоняем ширину колонок
                    for idx, col in enumerate(df.columns, 1):
                        max_length = max(
                            df[col].astype(str).map(len).max(),
                            len(str(col))
                        )
                        worksheet.column_dimensions[chr(64 + idx)].width = min(max_length + 2, 50)
                
                logger.success(f"✅ Результаты сохранены в: {output_file}")
                logger.info(f"📊 Всего строк: {len(df)}")
                logger.info(f"📋 Колонки: {', '.join(df.columns.tolist())}")
                
                # Статистика по заполненности
                if 'base_price' in df.columns:
                    filled = df['base_price'].notna().sum()
                    logger.info(f"💰 Заполнено цен: {filled} из {len(df)} ({filled/len(df)*100:.1f}%)")
                
            except Exception as e:
                logger.error(f"Ошибка при экспорте результатов: {e}")
                logger.exception("Детали ошибки:")
        else:
            logger.warning("Нет данных для экспорта")
        
        return 0
        
    except KeyboardInterrupt:
        logger.warning("Прервано пользователем")
        return 1
        
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}")
        logger.exception("Детали ошибки:")
        return 1


if __name__ == "__main__":
    sys.exit(main())

