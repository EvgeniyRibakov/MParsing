"""API клиент для Wildberries."""
import time
from typing import Dict, List, Optional
from loguru import logger
import requests


class WildberriesAPI:
    """Клиент для работы с официальным API Wildberries."""
    
    # Базовый URL для работы с товарами (suppliers API)
    BASE_URL = "https://suppliers-api.wildberries.ru"
    
    # Базовый URL для получения цен и скидок (discounts-prices API)
    PRICES_BASE_URL = "https://discounts-prices-api.wildberries.ru"
    
    def __init__(self, api_key: str, request_delay: float = 0.5):
        """Инициализация API клиента.
        
        Args:
            api_key: API ключ Wildberries
            request_delay: Задержка между запросами (секунды)
        """
        self.api_key = api_key
        self.request_delay = request_delay
        self.session = requests.Session()
        # Проверяем, есть ли префикс Bearer в ключе
        auth_header = api_key if api_key.startswith("Bearer ") else api_key
        self.session.headers.update({
            "Authorization": auth_header,
            "Content-Type": "application/json",
        })
    
    def _make_request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict] = None,
        json_data: Optional[Dict] = None,
        timeout: int = 30,
    ) -> Optional[Dict]:
        """Выполнить запрос к API.
        
        Args:
            method: HTTP метод (GET, POST, etc.)
            endpoint: Endpoint API
            params: Параметры запроса
            json_data: JSON данные для POST запросов
            timeout: Таймаут запроса
            
        Returns:
            Ответ API или None в случае ошибки
        """
        url = f"{self.BASE_URL}{endpoint}"
        
        try:
            response = self.session.request(
                method=method,
                url=url,
                params=params,
                json=json_data,
                timeout=timeout,
            )
            response.raise_for_status()
            
            # Задержка между запросами
            time.sleep(self.request_delay)
            
            return response.json()
            
        except requests.exceptions.RequestException as e:
            error_msg = str(e)
            if "Failed to resolve" in error_msg or "getaddrinfo failed" in error_msg:
                logger.error(f"Ошибка DNS/сети при запросе к {endpoint}: проверьте интернет-соединение")
            else:
                logger.error(f"Ошибка запроса к WB API {endpoint}: {e}")
            if hasattr(e, 'response') and e.response is not None:
                logger.error(f"Статус: {e.response.status_code}, Ответ: {e.response.text}")
            return None
    
    def get_content(self, limit: int = 1000, offset: int = 0) -> Optional[List[Dict]]:
        """Получить список товаров (контент).
        
        Args:
            limit: Количество товаров на странице (макс 1000)
            offset: Смещение для пагинации
            
        Returns:
            Список товаров или None
        """
        endpoint = "/content/v1/cards/cursor/list"
        params = {
            "limit": min(limit, 1000),
            "offset": offset,
        }
        
        result = self._make_request("POST", endpoint, json_data=params)
        
        if result and "data" in result:
            return result["data"].get("cards", [])
        
        return None
    
    def get_all_products(self) -> List[Dict]:
        """Получить все товары из кабинета.
        
        Returns:
            Список всех товаров
        """
        all_products = []
        offset = 0
        limit = 1000
        
        logger.info("Начинаем получение списка товаров из WB...")
        
        while True:
            products = self.get_content(limit=limit, offset=offset)
            
            if not products:
                break
            
            all_products.extend(products)
            logger.info(f"Получено товаров: {len(all_products)}")
            
            if len(products) < limit:
                break
            
            offset += limit
        
        logger.success(f"Всего получено товаров: {len(all_products)}")
        return all_products
    
    def _extract_article_from_url(self, article: str) -> str:
        """Извлечь артикул из URL или вернуть артикул как есть.
        
        Args:
            article: Артикул или URL вида https://www.wildberries.ru/catalog/115224606/detail.aspx
            
        Returns:
            Артикул (vendorCode)
        """
        import re
        # Если это URL, извлекаем артикул
        if article.startswith('http'):
            # Паттерн: /catalog/ЧИСЛО/detail.aspx
            match = re.search(r'/catalog/(\d+)/detail\.aspx', article)
            if match:
                return match.group(1)
            # Альтернативный паттерн: просто число в URL
            match = re.search(r'/(\d{6,})/', article)
            if match:
                return match.group(1)
        # Если это уже артикул, возвращаем как есть
        return str(article).strip()
    
    def get_prices_by_nm_id(self, nm_id: int) -> Optional[Dict]:
        """Получить цены для товара по nmID (номенклатура Wildberries).
        
        Использует GET /api/v2/list/goods/size/nm
        
        Args:
            nm_id: Номенклатура товара (nm_id)
            
        Returns:
            Информация о товаре с ценами или None
        """
        endpoint = "/api/v2/list/goods/size/nm"
        url = f"{self.PRICES_BASE_URL}{endpoint}"
        
        params = {
            "nm": nm_id
        }
        
        try:
            response = self.session.request(
                method="GET",
                url=url,
                params=params,
                timeout=30,
            )
            
            logger.info(f"📥 Ответ GET /api/v2/list/goods/size/nm для nmID {nm_id}: статус {response.status_code}")
            
            if response.status_code == 200:
                result = response.json()
                logger.success(f"✅ Успешно получены данные для nmID {nm_id}")
                return result
            else:
                logger.warning(f"⚠️ Статус {response.status_code}: {response.text[:200]}")
                return None
                
        except requests.exceptions.RequestException as e:
            logger.error(f"❌ Ошибка запроса для nmID {nm_id}: {e}")
            return None
    
    def get_prices_by_articles(self, articles: List[str]) -> Optional[List[Dict]]:
        """Получить цены для товаров по артикулам через эндпоинт /api/v2/list/goods/filter.
        
        Согласно документации: https://dev.wildberries.ru/openapi/work-with-products#tag/Ceny-i-skidki/paths/~1api~1v2~1list~1goods~1filter/get
        
        Стратегия:
        1. Получаем список товаров из кабинета для сопоставления vendorCode -> nmID
        2. Используем POST /api/v2/list/goods/filter с nmList (до 100 за запрос) - самый эффективный способ
        3. Если POST не работает, используем GET /api/v2/list/goods/filter с vendorCode (по одному артикулу)
        
        Лимиты API:
        - 10 запросов за 6 секунд
        - Минимальный интервал между запросами: 600 мс
        
        Args:
            articles: Список артикулов товаров (vendorCode) или URL
        
        Returns:
            Список товаров с ценами или None
        """
        endpoint = "/api/v2/list/goods/filter"
        url = f"{self.PRICES_BASE_URL}{endpoint}"
        
        # Извлекаем артикулы из URL (если это URL)
        cleaned_articles = [self._extract_article_from_url(art) for art in articles]
        logger.info(f"Обработка {len(cleaned_articles)} артикулов через эндпоинт {endpoint}")
        
        all_results = []
        request_count = 0
        start_time = time.time()
        min_interval = 0.6  # 600 миллисекунд между запросами
        
        # Проверяем, являются ли артикулы числовыми (возможно, это nmID)
        numeric_articles = [a for a in cleaned_articles if a.isdigit()]
        logger.info(f"📊 Найдено {len(numeric_articles)} числовых артикулов (возможно, это nmID)")
        
        # Шаг 1: Пробуем POST запрос с nmList (если артикулы числовые)
        if numeric_articles:
            logger.info("🔄 Пробуем POST запрос с nmList (предполагаем, что артикулы - это nmID)...")
            batch_size = 100
            
            for batch_idx in range(0, len(numeric_articles), batch_size):
                batch = numeric_articles[batch_idx:batch_idx + batch_size]
                nm_ids = [int(a) for a in batch]
                
                if request_count >= 10:
                    elapsed = time.time() - start_time
                    if elapsed < 6.0:
                        wait_time = 6.0 - elapsed
                        time.sleep(wait_time)
                    request_count = 0
                    start_time = time.time()
                
                json_data = {"nmList": nm_ids}  # Правильный формат: nmList, а не nmIDs
                batch_num = (batch_idx // batch_size) + 1
                total_batches = (len(numeric_articles) + batch_size - 1) // batch_size
                
                logger.info(f"📦 БАТЧ {batch_num}/{total_batches}: POST запрос с {len(nm_ids)} nmID")
                
                try:
                    response = self.session.request(
                        method="POST",
                        url=url,
                        json=json_data,
                        timeout=30,
                    )
                    
                    logger.info(f"📥 Ответ POST: статус {response.status_code}")
                    
                    if response.status_code == 200:
                        result = response.json()
                        if result:
                            if "data" in result:
                                data = result["data"]
                                if isinstance(data, dict) and "listGoods" in data:
                                    goods = data["listGoods"]
                                    logger.success(f"✅ Получено {len(goods)} товаров из listGoods")
                                    all_results.extend(goods)
                                elif isinstance(data, list):
                                    logger.success(f"✅ Получено {len(data)} товаров из data")
                                    all_results.extend(data)
                            elif isinstance(result, list):
                                logger.success(f"✅ Получено {len(result)} товаров")
                                all_results.extend(result)
                        
                        request_count += 1
                        time.sleep(min_interval)
                        # Успешно, переходим к следующему батчу
                    elif response.status_code == 400:
                        error_text = response.text
                        logger.warning(f"❌ POST вернул 400: {error_text}")
                        logger.debug(f"Полный ответ: {response.text}")
                        logger.debug(f"Заголовки запроса: {dict(self.session.headers)}")
                        logger.debug(f"URL: {url}")
                        logger.debug(f"Тело запроса: {json_data}")
                        # Продолжаем к получению списка товаров для сопоставления
                    elif response.status_code == 429:
                        retry_after = int(response.headers.get("Retry-After", 6))
                        logger.warning(f"Rate limit. Ожидание {retry_after} секунд...")
                        time.sleep(retry_after)
                        continue
                    else:
                        logger.warning(f"POST вернул статус {response.status_code}")
                        
                except requests.exceptions.RequestException as e:
                    logger.error(f"Ошибка POST запроса: {e}")
        
        # Шаг 2: Если POST запросы вернули данные, возвращаем результат
        if all_results:
            logger.success(f"🎉 Получено {len(all_results)} товаров через POST запросы с nmList")
            return all_results
        
        # Шаг 3: Если POST не сработал или вернул не все данные, пробуем GET с limit/offset
        logger.info("🔄 POST запросы не вернули данные, пробуем GET с limit/offset для получения всех товаров...")
        # Пробуем получить все товары через GET с limit/offset
        try:
            params = {"limit": 1000, "offset": 0}
            response = self.session.request(
                method="GET",
                url=url,
                params=params,
                timeout=30,
            )
            
            logger.info(f"📥 GET запрос (limit/offset): статус {response.status_code}")
            
            if response.status_code == 200:
                result = response.json()
                if result:
                    if "data" in result:
                        data = result["data"]
                        if isinstance(data, dict) and "listGoods" in data:
                            all_goods = data["listGoods"]
                            logger.success(f"✅ Получено {len(all_goods)} товаров через GET (limit/offset)")
                            
                            # Фильтруем по нужным артикулам
                            article_set = set(cleaned_articles)
                            filtered_goods = []
                            
                            for good in all_goods:
                                # Проверяем разные поля для артикула
                                good_article = (
                                    str(good.get("vendorCode", "")) or
                                    str(good.get("nmID", "")) or
                                    str(good.get("nmId", ""))
                                )
                                if good_article in article_set:
                                    filtered_goods.append(good)
                            
                            logger.info(f"📊 Найдено {len(filtered_goods)} товаров из {len(cleaned_articles)} запрошенных")
                            all_results.extend(filtered_goods)
                        elif isinstance(data, list):
                            logger.success(f"✅ Получено {len(data)} товаров")
                            all_results.extend(data)
            elif response.status_code == 400:
                error_text = response.text[:500]
                logger.warning(f"❌ GET (limit/offset) вернул 400: {error_text}")
            else:
                logger.warning(f"GET (limit/offset) вернул статус {response.status_code}")
        except requests.exceptions.RequestException as e:
            logger.error(f"Ошибка GET запроса (limit/offset): {e}")
        
        logger.success(f"🎉 Обработка завершена. Получено товаров: {len(all_results)}")
        return all_results if all_results else None
    
    def get_prices_by_nm_id(self, nm_id: int) -> Optional[Dict]:
        """Получить цены для всех размеров товара по nm_id.
        
        Args:
            nm_id: Номенклатура товара
            
        Returns:
            Информация о размерах с ценами или None
        """
        endpoint = f"/api/v2/list/goods/size/nm"
        
        url = f"{self.PRICES_BASE_URL}{endpoint}"
        params = {"nm": nm_id}
        
        try:
            response = self.session.request(
                method="GET",
                url=url,
                params=params,
                timeout=30,
            )
            response.raise_for_status()
            
            result = response.json()
            
            # Задержка между запросами
            time.sleep(self.request_delay)
            
            return result
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Ошибка запроса цен по nm_id {nm_id}: {e}")
            if hasattr(e, 'response') and e.response is not None:
                logger.error(f"Статус: {e.response.status_code}, Ответ: {e.response.text}")
            return None
    

