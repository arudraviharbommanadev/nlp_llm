import requests
import streamlit as st


API_URL = "http://localhost:8000/chat"
CONNECT_TIMEOUT_SECONDS = 10

st.set_page_config(page_title="Offline Ollama Chatbot", layout="centered")
st.title("Offline Ollama Chatbot")
st.caption("Streamlit frontend connected to a local FastAPI + Ollama backend.")

if "messages" not in st.session_state:
    st.session_state.messages = []

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

with st.form("chat_form", clear_on_submit=True):
    user_input = st.text_input("Message", placeholder="Ask something...")
    send_clicked = st.form_submit_button("Send")

if send_clicked and user_input.strip():
    user_input = user_input.strip()
    st.session_state.messages.append({"role": "user", "content": user_input})
    with st.chat_message("user"):
        st.markdown(user_input)

    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            try:
                response = requests.post(
                    API_URL,
                    json={"message": user_input},
                    timeout=(CONNECT_TIMEOUT_SECONDS, None),
                )
                response.raise_for_status()
                assistant_text = response.json()["response"]
            except requests.exceptions.Timeout:
                assistant_text = (
                    "The backend is taking longer than expected. "
                    "If this is the first request, Ollama may still be loading the model."
                )
            except requests.exceptions.RequestException as exc:
                assistant_text = f"Backend error: {exc}"

        st.markdown(assistant_text)

    st.session_state.messages.append({"role": "assistant", "content": assistant_text})
