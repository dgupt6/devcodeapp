import os
import re
import requests
import tempfile
import textwrap
import streamlit as st
import chromadb
from dotenv import load_dotenv
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import PyPDFLoader
from langchain_chroma import Chroma
from langchain.prompts import ChatPromptTemplate
from langchain.chains.combine_documents import create_stuff_documents_chain
from langchain.chains import create_retrieval_chain
from langchain_anthropic import ChatAnthropic
from langchain_openai import OpenAIEmbeddings, ChatOpenAI

class Config:
    CHUNK_SIZE = 200
    CHUNK_OVERLAP = 20
    MAX_TOKENS = 15000
    #MODEL_NAME = "gpt-4o-mini"
    TEMPERATURE = 0.4

class CodeProcessor:
    @staticmethod
    def clean_cpp_code(code):
        code = "\n".join([line for line in code.splitlines() if line.strip()])  # Remove empty lines
        code = textwrap.dedent(code)  # Normalize indentation
        code = re.sub(r"[ \t]+", " ", code)  # Remove excessive spaces
        return code

    @staticmethod
    def format_code_markdown(code):
        return f"```cpp\n{code}\n```"

class DocumentProcessor:
    @staticmethod
    def load_pdf(pdf_path):
        loader = PyPDFLoader(pdf_path)
        all_text = loader.load()
        return all_text

    @staticmethod
    def process_document(document):
        text_splitter = RecursiveCharacterTextSplitter(chunk_size=Config.CHUNK_SIZE, chunk_overlap=Config.CHUNK_OVERLAP)
        chunks = text_splitter.split_documents(document)
        #print(f"Number of text chunks after splitting: {len(chunks)}")
        #print("\nSample chunks:")
        #for i, chunk in enumerate(chunks[:3]):  # Print first 3 chunks as sample
        #    print(f"\nChunk {i + 1}:")
        #    print("-" * 50)
        #    print(chunk)  # Print first 200 characters of each chunk

        return chunks

class WebsiteProcessor:
    @staticmethod
    def fetch_html(url):
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        try:
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            return response.text
        except requests.RequestException as e:
            print(f"Error fetching the website: {e}")
            return None

    @staticmethod
    def process_website(url):
        html_content = WebsiteProcessor.fetch_html(url)
        if not html_content:
            raise ValueError("No content could be fetched from the website.")

        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.html') as temp_file:
            temp_file.write(html_content)
            temp_file_path = temp_file.name

        try:
            loader = BSHTMLLoader(temp_file_path)
            documents = loader.load()
        except ImportError:
            print("'lxml' is not installed. Falling back to built-in 'html.parser'.")
            loader = BSHTMLLoader(temp_file_path, bs_kwargs={'features': 'html.parser'})
            documents = loader.load()

        os.unlink(temp_file_path)

        print(f"\nNumber of documents loaded: {len(documents)}")
        if documents:
            print("Sample of loaded content:")
            print(documents[0].page_content[:200] + "...")
            print(f"Metadata: {documents[0].metadata}")

        text_splitter = RecursiveCharacterTextSplitter(chunk_size=Config.CHUNK_SIZE, chunk_overlap=Config.CHUNK_OVERLAP)
        chunks = text_splitter.split_documents(documents)
        print(f"Number of text chunks after splitting: {len(chunks)}")
        return chunks

class CodeReviewer:

    def __init__(self):
        load_dotenv()
        self.LlmModelName = 'Anthropic'
        #self.LlmModelName = 'OPENAI'
        self.llm = self.setup_llm()
        self.prompt= self.setup_prompt()
        self.retriever = self.setup_vector_store()
        self.qa_chain = create_stuff_documents_chain(self.llm, self.prompt)
        self.rag_chain = create_retrieval_chain(self.retriever, self.qa_chain)
    def setup_llm(self):
        if self.LlmModelName == 'OPENAI':
            OPENAI_API_KEY = st.secrets.get("OPENAI_API_KEY")
            #OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
            if not OPENAI_API_KEY :
                st.error("API keys are missing. Please check your `secrets.toml` file.")
                raise ValueError("API keys are missing.")
            llmModel = ChatOpenAI(model="gpt-4o", api_key=OPENAI_API_KEY)
        elif self.LlmModelName == 'Anthropic':
            anthropic_api_key = st.secrets.get("ANTHROPIC_API_KEY")
            #my_api_key = os.getenv("ANTHROPIC_API_KEY")
            if not anthropic_api_key:
                st.error("API keys are missing. Please check your `secrets.toml` file.")
                raise ValueError("API keys are missing.")
            llmModel= ChatAnthropic(
                model="claude-3-5-sonnet-latest",
                max_tokens=1000,
                temperature=0.7,
                anthropic_api_key=anthropic_api_key
            )
        else:
            llmModel = None

        return llmModel
    def setup_prompt(self):
        prompt = ChatPromptTemplate.from_messages(
            [
                ("system",
                 """
                 You are an AI Code Reviewer specializing in C++ programming, following the latest C++ Core Guidelines in the document . 
                 Your primary task is to analyze the given C++ code, identify potential improvements, and provide feedback on best practices.
                 Remember to mention the LLM model name that invoked in the review summary.

                 ### **Review Criteria:**
                 1. **Code Structure & Readability**
                     - Is the code well-structured and easy to read?
                     - Are meaningful names used for variables, functions, and classes?
                     - Is there unnecessary complexity?

                 2. **C++ Core Guidelines Compliance**
                     - Does the code adhere to best practices outlined in the C++ Core Guidelines document?
                     - Are proper memory management techniques followed (e.g., avoiding raw pointers)?
                     - Reference specific C++ Core Guidelines (example : F.4: If a function might have to be evaluated at compile time, declare it constexpr)
                     - Itis important to provide above specific reference..

                 3. **Const Correctness & Efficiency**
                     - Are `const` qualifiers used appropriately for function parameters and methods?
                     - Are function parameters passed efficiently (by `const&` or by value where applicable)?
                     - Are unnecessary copies avoided?

                 4. **Error Handling & Robustness**
                     - Are exceptions used where appropriate?
                     - Is input validation implemented to prevent invalid states?
                     - Are potential runtime errors (e.g., null dereferences, division by zero) accounted for?

                 5. **Performance Considerations**
                     - Does the code avoid unnecessary computations or redundant operations?
                     - Are STL containers and algorithms used effectively?
                     - Are appropriate data structures chosen for the task?

                 6. **Maintainability & Extensibility**
                     - Is the code modular and easy to extend?
                     - Are magic numbers and hardcoded values avoided?
                     - Are comments and documentation provided where necessary?

                 ### **Response Format:**
                 Provide a structured review with clear feedback and suggested improvements. Follow this format:

                 1. **General Summary:** A high-level assessment of the code.
                 2. **Strengths:** What the code does well.
                 3. **Issues & Suggestions:** Specific areas where the code can be improved, categorized by the criteria above.
                 4. **Final Score (1-10):** A compliance rating based on adherence to C++ best practices and C++ Core guidelines document.

                 ### **Additional Notes:**
                 - Be objective and constructive in your feedback.
                 - Avoid unnecessary jargon; explain improvements clearly.
                 - Reference specific C++ Core Guidelines where applicable.
                 - If the code follows best practices well, acknowledge it and suggest optional refinements.
                 {context}
                 """
                 ),
                ("human",
                 """
                     Please review the following C++ code :
                     {input}
                 """
                 )
            ]
        )

        return prompt

    def returnfilepath(self):
        # pdf_path = "/Users/devrajgupta/Downloads/" + filename + ".pdf"
        filename = "C++ Core Guidelines.pdf"  # PDF file name
        pdf_path = os.path.join(os.path.dirname(__file__), filename)  # Construct path relative to script location
        if not os.path.exists(pdf_path):
            st.error(f"PDF file not found at: {pdf_path}")
            raise FileNotFoundError(f"PDF file not found at: {pdf_path}")

        return pdf_path
    def setup_vector_store(self):
        chromadb.api.client.SharedSystemClient.clear_system_cache()
        chroma_client = chromadb.PersistentClient(path="./chroma_db")
        embeddings = OpenAIEmbeddings()
        pdf_path= self.returnfilepath()   # get the file path
        texts = DocumentProcessor.load_pdf(pdf_path)
        '''
        Processing C++ guideline document into chunks...
        '''
        chunks = DocumentProcessor.process_document(texts)
        vector_store = Chroma.from_documents(chunks,embeddings, persist_directory="./chroma_db")
        retriever = vector_store.as_retriever()
        st.success("✅ Vector store has been created.")
        st.success("✅ RAG pipeline setup completed.")
        return retriever

    def review_code(self, cpp_code):
        cleaned_code = CodeProcessor.clean_cpp_code(cpp_code)
        formatted_code = CodeProcessor.format_code_markdown(cleaned_code)
        response = self.rag_chain.invoke({"input": formatted_code})
        return response['answer']

class StreamlitApp:
    def __init__(self):
        st.title("📝 Welcome to AI-Powered C++ Code Reviewer using RAG")
        self.reviewer = CodeReviewer()

    def run(self):
        cpp_code = st.text_area("Paste your C++ code below and click **Review Code** to receive AI-generated feedback:",
                                height=200, placeholder="Type or paste your C++ code here...")

        if st.button("Review Code"):
            if cpp_code.strip():
                review_result = self.reviewer.review_code(cpp_code)
                st.subheader("🔹 AI Code Review:")
                st.code(review_result, language="cpp")
            else:
                st.warning("⚠️ Please enter some C++ code before submitting.")

        st.write("🚀 Built with Streamlit | AI-Powered C++ Code Review ( an 2025 V1.0) | Devraj Gupta")

if __name__ == "__main__":
    app = StreamlitApp()
    app.run()
