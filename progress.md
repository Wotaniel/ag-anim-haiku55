# AG-60517 · AdGuard v5 is here — прогресс

Статус: сборка готова, идёт публикация

- [x] Референс .keyshape разобран (формат: сек для abs-key-times, мс для playRange, пивот = translate группы + компенсатор)
- [x] Макеты найдены: ветка HAd3I2CYWl0dzYKKN5cKiC, кадры 3187:2995 (16:9) и 3187:3529 (9:16)
- [x] Выгрузка кусков из Figma (tools/fetch_figma.py) — 10 SVG + 2 эталонных рендера кадров
- [x] Сборка .keyshape ×2 (tools/build_keyshape.py)
- [x] Валидация (tools/validate_keyshape.py) — OK на обоих
- [x] Сверка с макетами: 16:9 — 0.15% пикселей расходится; 9:16 — 0.13%
- [x] Таймлайн по замерам масштаба: 16:9 ×1.10 (3 с), ×1.16 (6.6 с), ×1.0 (12 с); 9:16 ×1.05 / ×1.07
- [ ] git init → commit → push в main → Pages → curl проверка

Файлы: AG-60517_event-card-16x9.keyshape, AG-60517_event-details-9x16.keyshape, index.html
