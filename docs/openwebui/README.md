# Open WebUI Integration

## Goal
Use Open WebUI chat as the main UI for movie recommendations while preserving user-specific history (`user_id`).

## File
- `movie_recsys_tool.py` is a ready Open WebUI Function/Tool script.

## Add to Open WebUI
You can use the same file in both sections:
- Tools section (class Tools)
- Functions section (class Pipe)

## Option A: Tools section (recommended)
1. Open Open WebUI (`http://localhost:3000`).
2. Go to `Admin Panel` -> `Tools`.
3. Click `+ New Tool` and paste content from `movie_recsys_tool.py`.
4. Save and enable this function for your workspace/model.
5. In chat page, select any model at the top (`Выберите модель`).
6. Enable the function/tools for the current chat (tools icon near input).

## Option B: Functions section (if you prefer it)
1. Open `Admin Panel` -> `Functions`.
2. Click `+ New Function` and paste the same content from `movie_recsys_tool.py`.
3. Save and activate it.
4. In chat, use text format with optional user id:
	- `user_id=42: мрачный детектив про роботов`
5. In right panel `Управление -> Вентили` set `active_user_id`.
	- This value is per-user/per-chat valve and works as profile switch in UI.

## Set backend URL
In function settings (`Valves`):
- `api_base_url`: `http://host.docker.internal:8000`

If Open WebUI and backend are in one docker network, you can use:
- `http://movie_backend:8000`

## Choose user ID
You have two ways:
1. Set `active_user_id` in `Вентили` panel (right side in chat). This is the closest UI picker and works like profile switch.
2. Set `default_user_id` in function settings as fallback.
3. Explicitly choose active profile in chat using tool call:
	- `set_active_user_id(user_id=42)`
4. Override only for one query:
	- `recommend_movies(query_text="...", user_id=15)`

## Russian Description Translation
In Valves you can control description translation:
- `translate_descriptions_to_ru`: `true|false` (default: `true`)
- `translation_timeout_seconds`: timeout for translation request in seconds (default: `8`)

Useful check:
- `get_active_user_id()`

Example prompt:
- `Сначала вызови set_active_user_id(user_id=42), потом recommend_movies(query_text="мрачный детектив про роботов", top_k=20).`

## Recommended prompt pattern
- `Подбери 5 фильмов под запрос "космическая драма" для user_id=15 и коротко объясни каждый выбор.`

## Minimal Working Flow
1. `healthcheck_backend()`
2. `set_active_user_id(user_id=7)`
3. `recommend_movies(query_text="грустная научная фантастика", top_k=20)`

## Troubleshooting
- If you get `API error`, check backend: `http://localhost:8000/docs`.
- If container cannot reach host backend, keep `api_base_url=http://host.docker.internal:8000`.
