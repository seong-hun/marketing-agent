from typing import Annotated, List, Literal, TypedDict, Union
import operator
import json
import re
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage, ToolMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain.chat_models import init_chat_model
from langchain.tools import tool
from langgraph.graph import StateGraph, END, MessagesState
from langgraph.prebuilt import ToolNode
from langgraph.graph.message import add_messages

from domains.analysis.utils import get_korean_time_str
from domains.analysis.tools import tavily_search_youtube, get_youtube_transcript, read_local_file, write_local_file
from domains.analysis.prompt import SUPERVISOR_SYSTEM_PROMPT, YOUTUBE_ANALYST_SYSTEM_PROMPT, REPORT_WRITER_SYSTEM_PROMPT

execute_time = get_korean_time_str()

class AgentState(MessagesState):
    sender: str

supervisor_llm_base = init_chat_model(model="openai:gpt-4o-mini", temperature=0)
analyst_llm_base = init_chat_model(model="openai:gpt-4o-mini", temperature=0)
writer_llm_base = init_chat_model(model="openai:gpt-4o-mini", temperature=0)


# Transfer tools
@tool
def transfer_to_youtube_analyst(youtube_url: str, instruction: str) -> str:
    """Delegate to Youtube Analyst.
    
    Args

    Returns

    """
    return f"Delegating to Youtube Analyst... URL: {youtube_url}, Instruction: {instruction}"

@tool
def transfer_to_report_writer(instruction: str, context_files: List[str] = []) -> str:
    """Delegate to Youtube Analyst.
    
    Args

    Returns

    """
    return f"Delegating to Report Writer... Instruction: {instruction}, Context Files: {context_files}"

supervisor_tools = [tavily_search_youtube, transfer_to_youtube_analyst, transfer_to_report_writer]
supervisor_llm = supervisor_llm_base.bind_tools(supervisor_tools)

# YouTube Analyst Tools
analyst_tools = [get_youtube_transcript, read_local_file, write_local_file]
analyst_llm = analyst_llm_base.bind_tools(analyst_tools)

# Report Writer Tools
writer_tools = [read_local_file, write_local_file]
writer_llm = writer_llm_base.bind_tools(writer_tools)

def supervisor_node(state: AgentState) -> AgentState:
    messages = state["messages"]
    system_content = SUPERVISOR_SYSTEM_PROMPT.format(current_time = execute_time)

    response = supervisor_llm.invoke([SystemMessage(content=system_content)] + messages)
    return {"messages": [response], "sender": "Supervisor"}


def youtube_analyst_node(state: AgentState) -> AgentState:
    messages = state["messages"]
    system_content = YOUTUBE_ANALYST_SYSTEM_PROMPT.format(current_time=execute_time)
    
    response = analyst_llm.invoke([SystemMessage(content=system_content)] + messages)
    return {"messages": [response], "sender": "YouTubeAnalyst"}


def report_writer_node(state: AgentState) -> AgentState:
    """Report Writer Agent Node"""
    messages = state["messages"]
    system_content = REPORT_WRITER_SYSTEM_PROMPT.format(current_time=execute_time)

    user_query = "Unknown Query"
    for msg in messages:
        if isinstance(msg, HumanMessage):
            user_query = msg.content
            break
    
    instruction = "Review the conversation history, especailly the summary files created by the Analyst, and write a comprehensive final report."
    context_files = []
    transfer_index = -1

    #  transfer_to_report_writer tool calling 일 경우를 명시적 탐색
    for i, msg in reversed(list(enumerate(messages))):
        if isinstance(msg, AIMessage) and msg.tool_calls:
            for tc in msg.tool_calls:
                if tc["name"] == "transfer_to_report_writer":
                    args = tc["args"]
                    instruction = args.get("instruction", instruction)
                    context_files = args.get("context_files", [])
                    transfer_index = i
                    break
            if transfer_index != -1:
                break

    # need validation
    tool_extracted_files = set()
    for msg in messages:
        if isinstance(msg, AIMessage) and msg.tool_calls:
            for tc in msg.tool_calls:
                if tc["name"] == "write_local_file":
                    path = tc["args"].get("file_path")
                    if path:
                        tool_extracted_files.add(path)
    print(f'reporter: {tool_extracted_files}')
    #
    
    writer_input_content = f"""
    [Task]
    User Query: {user_query}
    """

    writer_session_messages = [SystemMessage(content=system_content), HumanMessage(content=writer_input_content)]
    
    response = writer_llm.invoke(writer_session_messages)
    return {"messages": [response], "sender": "ReportWriter"}

# 이미 llm을 tool로 binding했는데, 왜 추가적인 노드를 만드는 걸까
supervisor_tool_node = ToolNode(supervisor_tools)
analyst_tool_node = ToolNode(analyst_tools)
writer_tool_node = ToolNode(writer_tools)


# Routing

def should_continue_supervisor(state: AgentState) -> Literal["supervisor_tools", "ReportWriter"]:
    msg = state["messages"][-1]  # 마지막 메시지(어디로 가라)
    if isinstance(msg, AIMessage) and msg.tool_calls:
        return "supervisor_tools"
    return "ReportWriter"

def post_supervisor_tool_route(state: AgentState) -> Literal["YouTubeAnalyst", "ReportWriter", "Supervisor"]:
    msg = state["messages"][-1]
    if isinstance(msg, ToolMessage):
        if msg.name == "transfer_to_youtube_analyst":
            return "YouTubeAnalyst"
        elif msg.name == "transfer_to_reporter_writer":
            return "ReportWriter"
    return "Supervisor"

def should_continue_analyst(state: AgentState) -> Literal["analyst_tools", "Supervisor"]:
    msg = state["messages"][-1]
    if isinstance(msg, AIMessage) and msg.tool_calls:
        return "analyst_tools"
    return "Supervisor"

def should_continue_writer(state: AgentState) -> Literal["writer_tools", "__end__"]:
    msg = state["messages"][-1]
    if isinstance(msg, AIMessage) and msg.tool_calls:
        return "writer_tools"
    return "__end__"