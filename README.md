# AG-60517 · AdGuard v5 is here — анимация Event Card

Лёгкая цикличная анимация (луп 12 с) для App Store In-App Event. Два файла Keyshape:

- `AG-60517_event-card-16x9.keyshape` — 1920×1080 (Event Card)
- `AG-60517_event-details-9x16.keyshape` — 1080×1920 (Event Details)

Открыть в Keyshape: двойной клик по файлу (zip с `document.keyshapex`).

## Что анимировано

| Слой | Что делает |
| ---- | ---------- |
| `camera-zoom` | Камера пролётами: наезд → замереть → наезд → замереть → медленный отъезд (пивот — лицо) |
| `character-breath` | Дыхание: вертикальное растяжение груди ×1.008 каждые 4 с (пивот — грудь), без боковых сдвигов |
| `glow` | Свечение дышит в такт груди |
| `glint-crown` | Блик на короне: два коротких мерцания (3.3 с и 9.9 с) |
| `glint-blade-sheen` | Блик скользит по клинку (только 9:16, 6.5–8.6 с) |
| `ui` | Бейдж, заголовок, подзаголовок, чипы — статичны |

Таймлайн и амплитуды — в `tools/build_keyshape.py`.

## Структура

- `assets/pieces/` — SVG-куски из Figma (текст в контурах, без фильтров), `assets/meta.json` — координаты кусков
- `tools/fetch_figma.py` — выгрузка кусков через REST
- `tools/build_keyshape.py` — сборка `.keyshape` и `index.html`
- `tools/validate_keyshape.py` — проверка формата перед сдачей
- `preview/` — сверка с макетами Figma
- `index.html` — превью в браузере (SMIL-имитация той же модели), таймлайн, ссылки на файлы

## Формат

abs-key-times и ks:animate — в секундах; ks:playRangeIn/Out — в миллисекундах; timing-functions = ключей − 1; repeat-end="indefinite"; motion path абсолютный, первая точка = translate группы.
