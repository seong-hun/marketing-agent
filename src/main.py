import os
from dotenv import load_dotenv
from domains.analysis.graph import graph
from langchain_core.messages import HumanMessage

load_dotenv()


def run_agent(query: str):
    print(f"\n 리서치 시작: {query}")
    print("="*50)

    inputs = {
        "messages": [HumanMessage(content=query)]
    }

    for output in graph.stream(inputs, config={"recursion_limit": 20}):
        for node_name, state in output.items():
            print(f"\n[Node: {node_name}]")

            last_msg = state["messages"][-1]

            if hasattr(last_msg, "tool_calls") and last_msg.tool_calls:
                for tc in last_msg.tool_calls:
                    print(f" 도구 호출: {tc['name']}({tc['args']})")
            elif last_msg.content:
                # 너무 긴 내용은 잘라서 출력
                content = last_msg.content
                if len(content) > 300:
                    print(f" 내용: {content[:300]}... (이하 중략)")
                else:
                    print(f" 내용: {content}")
            print("-" * 30)

if __name__ == "__main__":
    user_query = input("Enter the query to research: ")
    run_agent(user_query)