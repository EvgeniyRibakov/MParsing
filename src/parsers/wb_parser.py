"""Парсер цен для Wildberries."""
from typing import Dict, List, Optional
from pathlib import Path
from loguru import logger
from src.api.wb_api import WildberriesAPI
from src.utils.articles_reader import read_wb_articles, find_articles_file


class WildberriesParser:
    """Парсер цен для Wildberries."""
    
    def __init__(self, api_key: str, cabinet_name: str, cabinet_id: str, request_delay: float = 0.5):
        """Инициализация парсера.
        
        Args:
            api_key: API ключ Wildberries
            cabinet_name: Название кабинета
            cabinet_id: ID кабинета
            request_delay: Задержка между запросами
        """
        self.cabinet_name = cabinet_name
        self.cabinet_id = cabinet_id
        self.api = WildberriesAPI(api_key, request_delay=request_delay)
    
    def parse_basic_prices(self, articles_file_path: Optional[Path] = None) -> List[Dict]:
        """Парсинг базовых цен через официальное API.
        
        Args:
            articles_file_path: Путь к файлу Articles.xlsx (если None, будет найден автоматически)
        
        Returns:
            Список товаров с базовыми ценами
        """
        logger.info(f"Начинаем парсинг базовых цен для кабинета {self.cabinet_name}...")
        
        # Читаем артикулы из Articles.xlsx
        if not articles_file_path:
            articles_file_path = find_articles_file()
        
        if not articles_file_path:
            logger.error("Не удалось найти файл Articles.xlsx")
            return []
        
        logger.info(f"Читаем артикулы из {articles_file_path}...")
        vendor_codes = read_wb_articles(articles_file_path)
        
        if not vendor_codes:
            logger.warning(f"Не найдено артикулов в файле Articles.xlsx")
            return []
        
        logger.info(f"Найдено артикулов для обработки: {len(vendor_codes)}")
        
        # Разбиваем на батчи по 100 артикулов (лимит API)
        batch_size = 100
        all_results = []
        
        for i in range(0, len(vendor_codes), batch_size):
            batch = vendor_codes[i:i + batch_size]
            batch_num = (i // batch_size) + 1
            total_batches = (len(vendor_codes) + batch_size - 1) // batch_size
            
            logger.info(f"Обработка батча {batch_num}/{total_batches} ({len(batch)} артикулов)...")
            
            # Получаем цены по артикулам через закреплённый эндпоинт
            prices_data = self.api.get_prices_by_articles(batch)
            
            if not prices_data:
                logger.warning(f"Не удалось получить цены для батча {batch_num}")
                # Добавляем товары без цен
                for vendor_code in batch:
                    all_results.append({
                        "cabinet": self.cabinet_name,
                        "cabinet_id": self.cabinet_id,
                        "vendor_code": vendor_code,
                        "base_price": None,
                        "discount_price": None,
                        "price_with_card": None,
                        "error": "Не удалось получить цены",
                    })
                continue
            
            # Обрабатываем полученные данные о ценах
            for price_item in prices_data:
                vendor_code = price_item.get("vendorCode") or price_item.get("vendor_code")
                nm_id = price_item.get("nmID") or price_item.get("nmId")
                
                # Структура API: данные о ценах находятся в массиве sizes
                # Каждый товар может иметь несколько размеров
                sizes = price_item.get("sizes", [])
                
                if sizes:
                    # Обрабатываем каждый размер отдельно
                    for size in sizes:
                        base_price = size.get("price")  # Базовая цена
                        discounted_price = size.get("discountedPrice")  # Цена со скидкой
                        club_discounted_price = size.get("clubDiscountedPrice")  # Цена с WB Клубом
                        size_id = size.get("sizeID")
                        tech_size_name = size.get("techSizeName", "")
                        
                        all_results.append({
                            "cabinet": self.cabinet_name,
                            "cabinet_id": self.cabinet_id,
                            "nm_id": nm_id,
                            "vendor_code": vendor_code,
                            "size_id": size_id,
                            "size_name": tech_size_name,
                            "base_price": base_price,
                            "discounted_price": discounted_price,
                            "club_discounted_price": club_discounted_price,
                            "discount_percent": price_item.get("discount"),
                            "club_discount_percent": price_item.get("clubDiscount"),
                            "currency": price_item.get("currencyIsoCode4217", "RUB"),
                            "editable_size_price": price_item.get("editableSizePrice", False),
                        })
                else:
                    # Если нет sizes, пробуем извлечь цены напрямую из товара
                    base_price = price_item.get("price")
                    discounted_price = price_item.get("discountedPrice")
                    club_discounted_price = price_item.get("clubDiscountedPrice")
                    
                    all_results.append({
                        "cabinet": self.cabinet_name,
                        "cabinet_id": self.cabinet_id,
                        "nm_id": nm_id,
                        "vendor_code": vendor_code,
                        "size_id": None,
                        "size_name": None,
                        "base_price": base_price,
                        "discounted_price": discounted_price,
                        "club_discounted_price": club_discounted_price,
                        "discount_percent": price_item.get("discount"),
                        "club_discount_percent": price_item.get("clubDiscount"),
                        "currency": price_item.get("currencyIsoCode4217", "RUB"),
                        "editable_size_price": price_item.get("editableSizePrice", False),
                    })
        
        logger.success(f"Обработано товаров: {len(all_results)}")
        return all_results
    
    def parse_card_prices(self) -> List[Dict]:
        """Парсинг цен с WB-картой через XPath (существующее решение).
        
        Returns:
            Список товаров с ценами с картой
        """
        logger.info(f"Начинаем парсинг цен с WB-картой для кабинета {self.cabinet_name}...")
        
        # TODO: Адаптировать существующее XPath-решение
        # Пока заглушка
        
        logger.warning("Парсинг цен с WB-картой ещё не реализован")
        return []
    
    def parse_spp_prices(self) -> List[Dict]:
        """Парсинг цен после СПП (чёрная цена) - требует research.
        
        Returns:
            Список товаров с ценами после СПП
        """
        logger.info(f"Начинаем парсинг цен после СПП для кабинета {self.cabinet_name}...")
        
        # TODO: Research - найти API или XPath для получения цены после СПП
        logger.warning("Парсинг цен после СПП требует research - не реализован")
        return []

