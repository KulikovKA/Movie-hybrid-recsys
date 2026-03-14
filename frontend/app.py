import streamlit as st
import requests

# Настройки страницы
st.set_page_config(page_title="Movie RecSys", page_icon="🍿", layout="centered")

st.title("🍿 Интеллектуальный поиск кино")
st.markdown("Введите, что бы вы хотели посмотреть, и наша гибридная система подберет фильмы, а нейросеть объяснит свой выбор!")

# Поля ввода
col1, col2 = st.columns([3, 1])
with col1:
    query_text = st.text_input("Ваш запрос:", placeholder="Например: хочу грустную драму про космос")
with col2:
    user_id = st.number_input("ID пользователя", min_value=1, value=1)

top_k = st.slider("Сколько фильмов показать?", min_value=1, max_value=10, value=5)

if st.button("Найти фильмы", type="primary"):
    if query_text:
        with st.spinner("Ищем лучшие совпадения и генерируем ответ AI..."):
            try:
                # Обращаемся к нашему бэкенду внутри Docker-сети
                response = requests.post(
                    "http://backend:8000/api/v1/recommend",
                    json={"user_id": user_id, "query_text": query_text, "top_k": top_k}
                )
                
                if response.status_code == 200:
                    data = response.json()
                    
                    # 1. Выводим объяснение от LLM
                    st.subheader("🤖 Комментарий нейросети:")
                    st.info(data.get("explanation", "Объяснение не получено."))
                    
                    # 2. Выводим список фильмов
                    st.subheader("🎬 Рекомендации:")
                    for idx, movie in enumerate(data.get("movies", [])):
                        st.markdown(f"**{idx + 1}. {movie['title']}**")
                        if movie.get('overview'):
                            st.caption(f"{movie['overview']}")
                        st.divider()
                        
                else:
                    st.error(f"Ошибка бэкенда: {response.text}")
            except Exception as e:
                st.error(f"Не удалось подключиться к серверу бэкенда: {e}")
    else:
        st.warning("Пожалуйста, введите запрос!")