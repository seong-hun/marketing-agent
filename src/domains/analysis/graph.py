from langgraph.graph import StateGraph, END
from domains.analysis.subagents.definitions import (
    AgentState,
    supervisor_node,
    youtube_analyst_node,
    report_writer_node,
    supervisor_tool_node,
    analyst_tool_node,
    writer_tool_node,
    should_continue_supervisor,
    post_supervisor_tool_route,
    should_continue_analyst,
    should_continue_writer
)


workflow = StateGraph(AgentState)

workflow.add_node("Supervisor", supervisor_node)
workflow.add_node("supervisor_tools", supervisor_tool_node)
workflow.add_node("YouTubeAnalyst", youtube_analyst_node)
workflow.add_node("analyst_tools", analyst_tool_node)
workflow.add_node("ReportWriter", report_writer_node)
workflow.add_node("writer_tools", writer_tool_node)


# Start -> Supervisor
workflow.set_entry_point("Supervisor")

# Supervisor -> (Decision) -> Tools or ReportWriter (End of Supervision)
workflow.add_conditional_edges(
    "Supervisor",
    should_continue_supervisor,
    {
        "supervisor_tools": "supervisor_tools",
        "ReportWriter": "ReportWriter"  # Supervisor finishes -> Writer starts
    }
)

# Supervisor Tools -> (Decision) -> YouTubeAnalyst, ReportWriter or Supervisor
workflow.add_conditional_edges(
    "supervisor_tools",
    post_supervisor_tool_route,
    {
        "YouTubeAnalyst": "YouTubeAnalyst",
        "ReportWriter": "ReportWriter",
        "Supervisor": "Supervisor"
    }
)

# YouTubeAnalyst -> (Decision) -> Analyst Tools or Supervisor
workflow.add_conditional_edges(
    "YouTubeAnalyst",
    should_continue_analyst,
    {
        "analyst_tools": "analyst_tools",
        "Supervisor": "Supervisor"
    }
)

# ReportWriter -> (Decision) -> Writer Tools or END
workflow.add_conditional_edges(
    "ReportWriter",
    should_continue_writer,
    {
        "writer_tools": "writer_tools",
        "__end__": END  # Writer finishes -> Process End
    }
)

# Tool Nodes -> Back to Agent
workflow.add_edge("analyst_tools", "YouTubeAnalyst")
workflow.add_edge("writer_tools", "ReportWriter")

# 4. 컴파일
graph = workflow.compile()
