import streamlit as st
import requests
import json

# Настройки страницы
st.set_page_config(
    page_title="Movie RecSys", 
    page_icon="🍿", 
    layout="wide"  # Широкий формат для удобного отображения карточек
)

st.title("🍿 Интеллектуальный поиск кино")
st.markdown("Система использует гибридный поиск (FAISS + ALS) и нейросеть Llama-3 для точной фильтрации и анализа.")

# Поля ввода
col_input, col_id = st.columns([3, 1])
with col_input:
    query_text = st.text_input("Ваш запрос:", placeholder="Например: Мрачный детектив про роботов")
with col_id:
    user_id = st.number_input("ID пользователя", min_value=1, value=1)

# Кнопка поиска
if st.button("Найти фильмы", type="primary"):
    if query_text:
        with st.spinner("Ищем лучшие совпадения и проводим AI-анализ..."):
            try:
                # Отправляем запрос на бэкенд (запрашиваем 20 кандидатов для фильтрации)
                response = requests.post(
                    "http://backend:8000/api/v1/recommend",
                    json={"user_id": user_id, "query_text": query_text, "top_k": 20}
                )
                
                if response.status_code == 200:
                    data = response.json()
                    
                    # --- 1. ОТОБРАЖЕНИЕ ИСТОРИИ (SIDEBAR) ---
                    user_history = data.get("user_history", [])
                    if user_history:
                        with st.sidebar:
                            st.header("🎬 Ваша история")
                            st.caption("Фильмы, которые вы оценили высоко:")
                            for movie_title in user_history:
                                st.text(f"• {movie_title}")
                            st.divider()

                    # --- 2. ТЕХНИЧЕСКИЙ ДЕБАГ (EXPANDER) ---
                    with st.expander("🛠 Техническая информация (JSON)"):
                        st.json(data)

                    # --- 3. ПАРСИНГ ОТВЕТА LLM ---
                    explanation_raw = data.get("explanation", "").strip()
                    parsed_data = {"recommendations": []}
                    
                    try:
                        # Глубокая очистка JSON от артефактов маркдауна
                        clean_json = explanation_raw
                        if "```json" in clean_json:
                            clean_json = clean_json.split("```json")[1].split("```")[0]
                        elif "```" in clean_json:
                            clean_json = clean_json.split("```")[1].split("```")[0]
                        
                        parsed_data = json.loads(clean_json.strip())
                    except Exception as e:
                        # Если не удалось распарсить как JSON, пробуем найти структуру внутри текста
                        st.error(f"🕵️‍♂️ Ошибка парсинга AI-ответа: {e}")
                        st.code(explanation_raw)

                    # --- 4. ВЫВОД РЕКОМЕНДАЦИЙ ---
                    llm_recs = parsed_data.get("recommendations", [])
                    
                    if not llm_recs:
                        # Случай, когда нейросеть-фильтр отклонила всех кандидатов
                        st.warning(f"🤖 Нейросеть проанализировала базу и не нашла фильмов, точно подходящих под запрос: '{query_text}'")
                        st.info("Попробуйте уточнить запрос (например, укажите жанр или страну).")
                        
                        # Фолбэк: показываем сырые результаты поиска
                        api_recs = data.get("recommendations", [])
                        if api_recs:
                            with st.expander("Посмотреть результаты без AI-фильтрации"):
                                for m in api_recs[:5]:
                                    st.text(f"• {m.get('title')}")
                    else:
                        st.subheader("🎯 Лучшие совпадения по мнению AI:")
                        
                        # Отображаем карточки сеткой по 3 в ряд
                        cols = st.columns(3)
                        for idx, rec in enumerate(llm_recs):
                            with cols[idx % 3]:
                                with st.container(border=True):
                                    st.markdown(f"### {rec.get('title', 'Без названия')}")
                                    st.caption(rec.get('description', 'Описание отсутствует'))
                                    st.divider()
                                    st.success(f"**💡 Почему подходит:**\n\n{rec.get('reason', 'Подходит под параметры')}")
                else:
                    st.error(f"Ошибка бэкенда: {response.status_code}")
            except Exception as e:
                st.error(f"Не удалось подключиться к серверу: {e}")
    else:
        st.warning("Пожалуйста, введите текст запроса!")