import os
import asyncio
from dotenv import load_dotenv
from pinecone import Pinecone
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_core.prompts import PromptTemplate
from langchain_groq import ChatGroq

load_dotenv()

PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
PINECONE_INDEX_NAME = os.getenv("PINECONE_INDEX_NAME", "rbac-diagnosis-index")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

os.environ["GOOGLE_API_KEY"] = GOOGLE_API_KEY

pc=Pinecone(api_key=PINECONE_API_KEY)
index=pc.Index(PINECONE_INDEX_NAME)

embed_model=GoogleGenerativeAIEmbeddings(model="models/embedding-001")
llm=ChatGroq(temperature=0,model_name="llama3-8b-8192",groq_api_key=GROQ_API_KEY)

prompt=PromptTemplate.from_template(
    """
You are a medical assistant. Using only the provided context (portions of the user's report), produce:
1) A concise probable diagnosis (1-2 lines)
2) Key findings from the report (bullet points)
3) Recommended next steps (tests/treatments) — label clearly as suggestions, not medical advice.

Context:
{context}

User question:
{question}
""")

rag_chain=prompt | llm

async def diagnosis_report(user:str,doc_id:str,question:str):
    # embed question
    embedding=await asyncio.to_thread(embed_model.embed_query,question)
    # query pinecone
    results=await asyncio.to_thread(index.query,vector=embedding,top_k=5,include_metadata=True)

    # filter for doc_id matches
    contexts=[]
    sources_set=set()
    for match in results.get("matches",[]):
        md=match.get("metadata",{})
        if md.get("doc_id") == doc_id:
            # take text snippet 
            text_snippet=md.get("text") or ""
            contexts.append(text_snippet)
            sources_set.add(md.get("source"))

    if not contexts:
        return {"diagnosis":None,"explanation":"No report contentindexed for this doc_id"}
    
    # limit context length
    context_text="/n/n".join(contexts[:5])

    # final call the rag chain
    final=await asyncio.to_thread(rag_chain.invoke,{"context":context_text,"question":question})

    return {"diagnosis":final.content,"sources":list(sources_set)}