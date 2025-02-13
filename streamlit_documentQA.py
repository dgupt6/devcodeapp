# ---------------------------------------------------------------------------------
# This program answers questions from the uploaded document
# Developed by Devraj Gupta
# Revision version : V1.1
# Date : Feb 12 2025
# ---------------------------------------------------------------------------------
import streamlit as st
from openai import OpenAI
import pdfplumber
from docx import Document
from io import BytesIO

# Show title and description.
st.title("📄 Document Question Answering Assistant 🚀")
st.write(
    "Upload a document below and ask a question about it – ChatGPT will answer! "
    "To use this app, you need to provide an OpenAI API key, which you can get "
    "[here](https://platform.openai.com/account/api-keys)."
)

# Sidebar for user input
st.sidebar.header('User Input ')

# Ask user for their OpenAI API key via `st.text_input`.
input_api_key = st.sidebar.text_input("OpenAI API Key", type="password")
# About section
st.sidebar.header('About')
st.sidebar.info(
    "This application questions answers from uploaded document using LLM models."
    "\n"
    "Contact Devraj Gupta for suggestions/improvements!!"
)
if not input_api_key:
    st.info("Please add your OpenAI API key to continue.", icon="🗝️")
else:
    if input_api_key.upper() == 'DEFAULT':
        OPENAI_API_KEY = st.secrets.get("OPENAI_API_KEY")
    else:
        OPENAI_API_KEY = input_api_key
    # Create an OpenAI client.
    client = OpenAI(api_key=OPENAI_API_KEY)

    # File uploader for PDF, TXT, and DOCX files
    uploaded_file = st.file_uploader(
        "Upload a PDF, TXT, or DOCX file",
        type=["pdf", "txt", "docx"],
        accept_multiple_files=False
    )

    if uploaded_file is not None:
        # Display file details
        st.write(f"File Name: {uploaded_file.name}")
        st.write(f"File Type: {uploaded_file.type}")

        # Initialize text variable
        text = ""

        # Process PDF files using pdfplumber
        if uploaded_file.type == "application/pdf":
            st.success("Processing PDF file...")
            with pdfplumber.open(uploaded_file) as pdf:
                for page in pdf.pages:
                    text += page.extract_text() + "\n"

        # Process TXT files
        elif uploaded_file.type == "text/plain":
            st.success("Processing TXT file...")
            text = uploaded_file.read().decode("utf-8")

        # Process DOCX files
        elif uploaded_file.type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
            st.success("Processing DOCX file...")
            doc = Document(BytesIO(uploaded_file.read()))
            for paragraph in doc.paragraphs:
                text += paragraph.text + "\n"

        # Ask the user for a question
        question = st.text_area(
            "Now ask a question about the document!",
            placeholder="Can you give me a short summary?",
            disabled=not text,
        )

        if text and question:
            context = text
            messages = [
                {
                    "role": "system",
                    "content": "You are a helpful assistant that answers questions about the uploaded document only. "
                               "If enough information is not present in the document, say 'I don't know the answer to "
                               "this question'."
                },
                {
                    "role": "user",
                    "content": f"Here's the document as context: {context} \n\n---\n\n {question}",
                }
            ]

            # Generate an answer using the OpenAI API.
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=messages,
                stream=True,
            )

            # Stream the response to the app using `st.write_stream`.
            st.write_stream(response)

            st.write("🚀 Built with Streamlit | Feb 2025 V1.0 | Devraj Gupta")