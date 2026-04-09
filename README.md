# bitgn_agent

AI-агент для бенчмарка [BitGN PAC1](https://api.bitgn.com) — персональный ассистент управления знаниями, работающий поверх PCM-рантайма.

## Структура проекта

```
├── agent.py              # Standalone-агент (legacy, без eval-фреймворка)
├── run_eval.py           # Точка входа для запуска eval
├── configs/              # YAML-конфиги для запуска (модель, бенчмарк, прототип)
├── prototypes/           # Реализации агентов
│   ├── base.py           # Базовый класс BaseAgent
│   ├── baseline/         # Baseline-прототип (structured output, OpenAI)
│   ├── react_langchain_v1..v7/  # ReAct-прототипы на LangChain
│   └── react_deepagents_v1/     # Прототип на DeepAgents
├── eval/
│   ├── runner.py         # Оркестратор eval: загрузка задач, параллельный запуск, скоринг
│   └── run_logger.py     # Логирование результатов в файлы
├── logs/                 # Результаты прогонов
└── docs/
```

## Требования

- Python >= 3.13
- [uv](https://docs.astral.sh/uv/) (менеджер пакетов)

## Установка

```bash
# Клонировать репозиторий
git clone <repo-url>
cd bitgn_agent

# Установить зависимости
uv sync
```

## Переменные окружения

Создайте файл `.env` в корне проекта:

```env
OPENROUTER_API_KEY=...        # API-ключ OpenRouter (для standalone agent.py)
OPENAI_API_KEY=...            # API-ключ OpenAI (для прототипов на LangChain/OpenAI)
BENCHMARK_HOST=https://api.bitgn.com  # Хост BitGN (опционально, по умолчанию api.bitgn.com)
LANGSMITH_API_KEY=...         # API-ключ LangSmith для трейсинга (опционально)
HINT=...                      # Подсказка, добавляемая в system prompt (опционально)
```

## Запуск eval

```bash
# Запуск с конфигом по умолчанию (configs/baseline.yaml)
uv run python run_eval.py

# Запуск с указанным конфигом
uv run python run_eval.py configs/react_langchain_v7.yaml

# Запуск конкретных задач
uv run python run_eval.py configs/baseline.yaml task_1 task_2
```

### Формат конфига

```yaml
prototype: baseline                # имя прототипа из prototypes/
model: gpt-4.1-2025-04-14         # модель для LLM
benchmark: bitgn/pac1-dev         # ID бенчмарка
concurrency: 3                    # параллельность запуска задач
# task_ids: [task_1, task_2]      # фильтр по задачам (опционально)
```

## Запуск standalone-агента

`agent.py` — самостоятельный агент без eval-обвязки, работает через OpenRouter:

```bash
uv run python agent.py
```

## Создание нового прототипа

1. Создайте директорию `prototypes/<name>/`
2. Добавьте `__init__.py` с классом `Agent`, наследующим `BaseAgent`
3. Реализуйте метод `async run(harness_url, instruction, config)`
4. Создайте конфиг `configs/<name>.yaml` с `prototype: <name>`

## Логи

Результаты каждого прогона сохраняются в `logs/` и дублируются в LangSmith (если настроен `LANGSMITH_API_KEY`).
