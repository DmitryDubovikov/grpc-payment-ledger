# Введение в проект Payment Ledger

## Обзор

Payment Ledger — это микросервис для обработки платежей, построенный на основе gRPC. Сервис реализует паттерн двойной записи (double-entry ledger) для учёта финансовых операций и обеспечивает идемпотентность платежей.

## Что такое gRPC

gRPC (gRPC Remote Procedure Calls) — это высокопроизводительный фреймворк для межсервисного взаимодействия, разработанный Google. В отличие от REST API, где обмен данными происходит через JSON, gRPC использует:

- **Protocol Buffers (protobuf)** — бинарный формат сериализации данных
- **HTTP/2** — протокол с поддержкой мультиплексирования и сжатия заголовков
- **Строгая типизация** — контракт API определяется в `.proto` файлах

### Преимущества gRPC перед REST

| Характеристика | gRPC | REST |
|----------------|------|------|
| Формат данных | Бинарный (protobuf) | Текстовый (JSON) |
| Производительность | Высокая | Средняя |
| Типизация | Строгая, на этапе компиляции | Опциональная (OpenAPI) |
| Streaming | Встроенная поддержка | Требует WebSocket |
| Генерация кода | Автоматическая | Опциональная |

## Структура проекта

```
grpc-payment-ledger/
├── proto/                          # [ПИШЕТСЯ ВРУЧНУЮ] Определения протокола
│   └── payment/v1/
│       └── payment.proto           # Контракт API — исходный файл
├── src/
│   └── payment_service/
│       ├── api/
│       │   └── grpc_handlers.py    # [ПИШЕТСЯ ВРУЧНУЮ] Обработчики gRPC
│       ├── application/
│       │   ├── services.py         # [ПИШЕТСЯ ВРУЧНУЮ] Бизнес-логика
│       │   └── unit_of_work.py     # [ПИШЕТСЯ ВРУЧНУЮ] Паттерн Unit of Work
│       ├── domain/
│       │   └── models.py           # [ПИШЕТСЯ ВРУЧНУЮ] Доменные модели
│       ├── infrastructure/
│       │   ├── database.py         # [ПИШЕТСЯ ВРУЧНУЮ] Подключение к БД
│       │   └── repositories/       # [ПИШЕТСЯ ВРУЧНУЮ] Репозитории данных
│       ├── proto/                  # [АВТОГЕНЕРИРУЕТСЯ] из payment.proto
│       │   └── payment/v1/
│       │       ├── payment_pb2.py      # Классы сообщений
│       │       └── payment_pb2_grpc.py # Классы сервисов
│       ├── grpc_server.py          # [ПИШЕТСЯ ВРУЧНУЮ] Настройка сервера
│       └── main.py                 # [ПИШЕТСЯ ВРУЧНУЮ] Точка входа
├── tests/                          # [ПИШЕТСЯ ВРУЧНУЮ] Тесты
├── alembic/                        # [ПИШЕТСЯ ВРУЧНУЮ] Миграции БД
└── scripts/
    └── generate_proto.sh           # Скрипт генерации кода
```

> **Важно:** Только файлы в `src/payment_service/proto/` генерируются автоматически.
> Всё остальное, включая сам `payment.proto`, пишется разработчиком вручную.

## Определение API в proto-файле (пишется вручную)

Файл [payment.proto](../proto/payment/v1/payment.proto) — это **исходный файл, который пишется вручную**. Он определяет контракт между клиентом и сервером: какие методы доступны, какие данные принимают и возвращают.

### Процесс разработки gRPC API

```
┌─────────────────────────────────────────────────────────────────────┐
│  1. Разработчик пишет payment.proto                                │
│     (определяет сервисы, методы, сообщения)                        │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│  2. Запускает ./scripts/generate_proto.sh                          │
│     (компилятор protoc генерирует Python-код)                      │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│  3. Получает автогенерированные файлы:                             │
│     - payment_pb2.py — классы сообщений                            │
│     - payment_pb2_grpc.py — базовые классы сервисов                │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│  4. Разработчик пишет реализацию сервиса (grpc_handlers.py)        │
│     наследуясь от сгенерированного PaymentServiceServicer          │
└─────────────────────────────────────────────────────────────────────┘
```

### Определение сервиса

В proto-файле разработчик описывает, какие методы будет предоставлять сервис:

```protobuf
service PaymentService {
  // Авторизация платежа (идемпотентная операция)
  rpc AuthorizePayment(AuthorizePaymentRequest) returns (AuthorizePaymentResponse);

  // Получение информации о платеже
  rpc GetPayment(GetPaymentRequest) returns (GetPaymentResponse);

  // Получение баланса счёта
  rpc GetAccountBalance(GetAccountBalanceRequest) returns (GetAccountBalanceResponse);
}
```

Сервис определяет три **unary** метода (запрос-ответ). gRPC также поддерживает streaming, но в данном проекте он не используется.

### Определение сообщений

Сообщения (messages) — это структуры данных, которые передаются между клиентом и сервером:

```protobuf
message AuthorizePaymentRequest {
  string idempotency_key = 1;      // Ключ идемпотентности (UUID)
  string payer_account_id = 2;     // ID плательщика
  string payee_account_id = 3;     // ID получателя
  int64 amount_cents = 4;          // Сумма в копейках
  string currency = 5;             // Валюта (ISO 4217)
  string description = 6;          // Описание платежа
}

message AuthorizePaymentResponse {
  string payment_id = 1;           // ID созданного платежа
  PaymentStatus status = 2;        // Статус авторизации
  PaymentError error = 3;          // Ошибка (если есть)
  string processed_at = 4;         // Время обработки
}
```

Числа после `=` — это номера полей для бинарной сериализации. Они должны быть уникальными и неизменными.

### Перечисления (enum)

```protobuf
enum PaymentStatus {
  PAYMENT_STATUS_UNSPECIFIED = 0;  // Значение по умолчанию
  PAYMENT_STATUS_AUTHORIZED = 1;   // Платёж авторизован
  PAYMENT_STATUS_DECLINED = 2;     // Платёж отклонён
  PAYMENT_STATUS_DUPLICATE = 3;    // Повторный запрос (идемпотентность)
}

enum PaymentErrorCode {
  PAYMENT_ERROR_CODE_UNSPECIFIED = 0;
  PAYMENT_ERROR_CODE_INSUFFICIENT_FUNDS = 1;   // Недостаточно средств
  PAYMENT_ERROR_CODE_ACCOUNT_NOT_FOUND = 2;    // Счёт не найден
  PAYMENT_ERROR_CODE_INVALID_AMOUNT = 3;       // Некорректная сумма
  PAYMENT_ERROR_CODE_SAME_ACCOUNT = 4;         // Перевод на тот же счёт
  PAYMENT_ERROR_CODE_CURRENCY_MISMATCH = 5;    // Несовпадение валют
  PAYMENT_ERROR_CODE_RATE_LIMITED = 6;         // Превышен лимит запросов
}
```

В protobuf первое значение enum всегда должно быть `0` и обычно означает "не указано".

## Генерация кода (автоматически)

После того как разработчик написал `.proto` файл, необходимо сгенерировать Python-код. Это делается скриптом [generate_proto.sh](../scripts/generate_proto.sh):

```bash
python -m grpc_tools.protoc \
    -I./proto \
    --python_out=./src/payment_service/proto \
    --pyi_out=./src/payment_service/proto \
    --grpc_python_out=./src/payment_service/proto \
    ./proto/payment/v1/payment.proto
```

> **Важно:** Сгенерированные файлы **нельзя редактировать вручную** — при следующей генерации все изменения будут потеряны. Если нужно изменить API, редактируйте `payment.proto` и перегенерируйте код.

Генерируются три файла:
- `payment_pb2.py` — классы сообщений (`AuthorizePaymentRequest`, `Payment` и т.д.)
- `payment_pb2.pyi` — type hints для IDE (автодополнение, проверка типов)
- `payment_pb2_grpc.py` — базовые классы сервиса и клиентские stub'ы

### Что содержит сгенерированный код

**payment_pb2.py** — классы для работы с данными:
```python
# Создание запроса (автогенерированный класс)
request = payment_pb2.AuthorizePaymentRequest(
    idempotency_key="...",
    payer_account_id="acc-001",
    amount_cents=10000,
)

# Доступ к полям
print(request.amount_cents)  # 10000
```

**payment_pb2_grpc.py** — классы для сервера и клиента:
```python
# PaymentServiceServicer — базовый класс для сервера (нужно унаследовать и реализовать методы)
# PaymentServiceStub — клиент для вызова методов
# add_PaymentServiceServicer_to_server() — функция регистрации сервиса
```

## Реализация сервера (пишется вручную)

После генерации кода разработчик пишет реализацию сервиса. Это включает:
1. Настройку gRPC сервера
2. Реализацию методов сервиса (handlers)

### Настройка gRPC сервера

Файл [grpc_server.py](../src/payment_service/grpc_server.py) — **пишется вручную**. Содержит конфигурацию сервера:

```python
class GrpcServer:
    def __init__(self, database: Database) -> None:
        self._database = database
        self._server: grpc.aio.Server | None = None
        self._health_servicer = health.HealthServicer()

    async def start(self, port: int = 50051) -> None:
        # Создание асинхронного сервера с настройками размера сообщений
        self._server = grpc.aio.server(
            options=[
                ("grpc.max_send_message_length", 50 * 1024 * 1024),  # 50 МБ
                ("grpc.max_receive_message_length", 50 * 1024 * 1024),
            ]
        )

        # Регистрация обработчика PaymentService
        payment_handler = PaymentServiceHandler(self._database)
        payment_pb2_grpc.add_PaymentServiceServicer_to_server(
            payment_handler, self._server
        )

        # Регистрация сервиса Health Check
        health_pb2_grpc.add_HealthServicer_to_server(
            self._health_servicer, self._server
        )

        # Включение gRPC Reflection для отладки
        reflection.enable_server_reflection(service_names, self._server)

        # Запуск на всех интерфейсах
        self._server.add_insecure_port(f"[::]:{port}")
        await self._server.start()
```

Ключевые особенности:
- **`grpc.aio.server`** — асинхронный сервер на базе asyncio
- **Health Check** — стандартный протокол для проверки здоровья сервиса
- **Reflection** — позволяет клиентам (например, grpcurl) узнавать структуру API

### Обработчики запросов

Файл [grpc_handlers.py](../src/payment_service/api/grpc_handlers.py) — **пишется вручную**. Здесь разработчик реализует логику каждого метода, наследуясь от автогенерированного базового класса:

```python
# PaymentServiceServicer — автогенерированный базовый класс
# PaymentServiceHandler — наша реализация (пишется вручную)
class PaymentServiceHandler(payment_pb2_grpc.PaymentServiceServicer):
    """Обработчик gRPC запросов для PaymentService"""

    def __init__(self, database: Database) -> None:
        self._database = database

    async def AuthorizePayment(
        self,
        request: payment_pb2.AuthorizePaymentRequest,
        context: grpc.aio.ServicerContext,
    ) -> payment_pb2.AuthorizePaymentResponse:
        """Авторизация платежа"""

        # Валидация обязательных полей
        if not request.idempotency_key:
            await context.abort(
                grpc.StatusCode.INVALID_ARGUMENT,
                "idempotency_key is required",
            )

        # Работа с базой данных через Unit of Work
        async with self._database.session() as session:
            uow = UnitOfWork(session)
            payment_service = PaymentService(uow)

            cmd = AuthorizePaymentCommand(
                idempotency_key=request.idempotency_key,
                payer_account_id=request.payer_account_id,
                payee_account_id=request.payee_account_id,
                amount_cents=request.amount_cents,
                currency=request.currency,
                description=request.description or None,
            )

            result = await payment_service.authorize_payment(cmd)

        # Формирование ответа
        return payment_pb2.AuthorizePaymentResponse(
            payment_id=result.payment_id,
            status=STATUS_MAP.get(result.status),
            error=error,
            processed_at=result.processed_at.isoformat(),
        )
```

### Обработка ошибок

gRPC использует стандартные коды статусов. В проекте используются:

```python
# Некорректный запрос
await context.abort(
    grpc.StatusCode.INVALID_ARGUMENT,
    "idempotency_key is required",
)

# Ресурс не найден
await context.abort(
    grpc.StatusCode.NOT_FOUND,
    f"Payment {request.payment_id} not found",
)
```

Основные коды статусов gRPC:
- `OK` (0) — успех
- `INVALID_ARGUMENT` (3) — некорректные параметры
- `NOT_FOUND` (5) — ресурс не найден
- `ALREADY_EXISTS` (6) — ресурс уже существует
- `PERMISSION_DENIED` (7) — нет прав доступа
- `INTERNAL` (13) — внутренняя ошибка сервера
- `UNAVAILABLE` (14) — сервис недоступен

## Маппинг между доменными и protobuf типами (пишется вручную)

В хорошо спроектированном приложении доменные модели не зависят от protobuf. Поэтому в handlers нужно вручную преобразовывать типы:

```python
# Коды ошибок: строка -> enum protobuf
ERROR_CODE_MAP = {
    "INSUFFICIENT_FUNDS": payment_pb2.PAYMENT_ERROR_CODE_INSUFFICIENT_FUNDS,
    "ACCOUNT_NOT_FOUND": payment_pb2.PAYMENT_ERROR_CODE_ACCOUNT_NOT_FOUND,
    "INVALID_AMOUNT": payment_pb2.PAYMENT_ERROR_CODE_INVALID_AMOUNT,
    "SAME_ACCOUNT": payment_pb2.PAYMENT_ERROR_CODE_SAME_ACCOUNT,
    "CURRENCY_MISMATCH": payment_pb2.PAYMENT_ERROR_CODE_CURRENCY_MISMATCH,
    "RATE_LIMITED": payment_pb2.PAYMENT_ERROR_CODE_RATE_LIMITED,
}

# Статусы платежа: доменный enum -> enum protobuf
STATUS_MAP = {
    PaymentStatus.AUTHORIZED: payment_pb2.PAYMENT_STATUS_AUTHORIZED,
    PaymentStatus.DECLINED: payment_pb2.PAYMENT_STATUS_DECLINED,
    PaymentStatus.DUPLICATE: payment_pb2.PAYMENT_STATUS_DUPLICATE,
}
```

Это разделение позволяет изменять внутреннюю логику независимо от API контракта.

## Тестирование gRPC сервиса

### С помощью grpcurl

```bash
# Просмотр доступных сервисов (требуется reflection)
grpcurl -plaintext localhost:50051 list

# Просмотр методов сервиса
grpcurl -plaintext localhost:50051 list payment.v1.PaymentService

# Вызов метода авторизации платежа
grpcurl -plaintext -d '{
  "idempotency_key": "550e8400-e29b-41d4-a716-446655440000",
  "payer_account_id": "acc-001",
  "payee_account_id": "acc-002",
  "amount_cents": 10000,
  "currency": "RUB"
}' localhost:50051 payment.v1.PaymentService/AuthorizePayment

# Проверка здоровья сервиса
grpcurl -plaintext localhost:50051 grpc.health.v1.Health/Check
```

### С помощью Python-клиента

```python
import grpc
from payment_service.proto.payment.v1 import payment_pb2, payment_pb2_grpc

async def main():
    # Создание канала
    async with grpc.aio.insecure_channel("localhost:50051") as channel:
        # Создание stub (клиента)
        stub = payment_pb2_grpc.PaymentServiceStub(channel)

        # Вызов метода
        request = payment_pb2.AuthorizePaymentRequest(
            idempotency_key="550e8400-e29b-41d4-a716-446655440000",
            payer_account_id="acc-001",
            payee_account_id="acc-002",
            amount_cents=10000,
            currency="RUB",
        )

        response = await stub.AuthorizePayment(request)
        print(f"Payment ID: {response.payment_id}")
        print(f"Status: {response.status}")
```

## Архитектура приложения

```
┌─────────────────────────────────────────────────────────────┐
│                      gRPC Client                            │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    gRPC Server                              │
│  ┌─────────────────────────────────────────────────────┐   │
│  │              PaymentServiceHandler                   │   │
│  │  - Валидация запросов                               │   │
│  │  - Преобразование protobuf <-> domain              │   │
│  │  - Обработка gRPC ошибок                           │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                   Application Layer                         │
│  ┌─────────────────────────────────────────────────────┐   │
│  │                 PaymentService                       │   │
│  │  - Бизнес-логика авторизации платежей              │   │
│  │  - Проверка идемпотентности                        │   │
│  │  - Создание записей в ledger                       │   │
│  └─────────────────────────────────────────────────────┘   │
│  ┌─────────────────────────────────────────────────────┐   │
│  │                  UnitOfWork                          │   │
│  │  - Управление транзакциями                          │   │
│  │  - Координация репозиториев                        │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                  Infrastructure Layer                       │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐  │
│  │  Accounts    │  │  Payments    │  │   Ledger         │  │
│  │  Repository  │  │  Repository  │  │   Repository     │  │
│  └──────────────┘  └──────────────┘  └──────────────────┘  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐  │
│  │  Balance     │  │ Idempotency  │  │   Outbox         │  │
│  │  Repository  │  │  Repository  │  │   Repository     │  │
│  └──────────────┘  └──────────────┘  └──────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                      PostgreSQL                             │
└─────────────────────────────────────────────────────────────┘
```

## Ключевые паттерны проекта

### Идемпотентность

Каждый запрос на авторизацию платежа содержит `idempotency_key`. Если платёж с таким ключом уже был обработан, сервис возвращает статус `DUPLICATE` с данными исходного платежа:

```protobuf
enum PaymentStatus {
  PAYMENT_STATUS_DUPLICATE = 3;  // Повторный запрос
}
```

### Double-Entry Ledger

Каждый платёж создаёт две записи в ledger:
- **DEBIT** — списание со счёта плательщика
- **CREDIT** — зачисление на счёт получателя

Это гарантирует целостность финансовых данных.

### Health Check

Сервис реализует стандартный gRPC Health Check протокол:

```python
self._health_servicer.set("", health_pb2.HealthCheckResponse.SERVING)
self._health_servicer.set(
    "payment.v1.PaymentService",
    health_pb2.HealthCheckResponse.SERVING,
)
```

Это позволяет Kubernetes и другим оркестраторам проверять состояние сервиса.

## Запуск проекта

```bash
# Установка зависимостей
uv sync

# Генерация protobuf кода
./scripts/generate_proto.sh

# Запуск PostgreSQL и других зависимостей
docker-compose up -d

# Применение миграций
alembic upgrade head

# Запуск сервера
python -m payment_service.main
```

## Зависимости gRPC

В проекте используются следующие библиотеки:

```toml
[dependencies]
grpcio = ">=1.60.0"              # Основной фреймворк gRPC
grpcio-tools = ">=1.60.0"        # Компилятор protobuf
grpcio-reflection = ">=1.60.0"   # Поддержка reflection API
grpcio-health-checking = ">=1.60.0"  # Health Check протокол
```

## Дальнейшее изучение

- [Официальная документация gRPC](https://grpc.io/docs/)
- [Protocol Buffers Language Guide](https://protobuf.dev/programming-guides/proto3/)
- [gRPC Python Tutorial](https://grpc.io/docs/languages/python/basics/)
- [gRPC Health Checking Protocol](https://github.com/grpc/grpc/blob/master/doc/health-checking.md)
