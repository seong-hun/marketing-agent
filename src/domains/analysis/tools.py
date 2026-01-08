import os
import json
from pathlib import Path
from typing import TypedDict, Optional, Any, Dict, Annotated, Literal
from dotenv import load_dotenv

from langchain import tools
from langchain_core.tools import tool
from langchain_core.tools import InjectedToolArg
from tavily import TavilyClient
from googleapiclient.discovery import build
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api.formatters import TextFormatter
from markdownify import markdownify
import httpx

from domains.analysis.utils import clean_filename

load_dotenv()

tavily_client = TavilyClient()

WORKSPACE_ROOT = Path("workspace").resolve()
TRANSCRIPT_DIR = WORKSPACE_ROOT / "transcripts"


# 웹 검색 도구 (Tavily Search)
@tool
def tavily_search_youtube(
    query: str,
    max_results: Annotated[int, InjectedToolArg] = 3) -> str:
    """
    performs a web search using Tavily especially YouTube.
    Returns search results with content snippets.
    """
    try:
        results = tavily_client.search(
            query,
            max_results=max_results,
            include_domains=['https://www.youtube.com/'],
            exclude_domains=['https://www.youtube.com/shorts', 'https://www.youtube.com/playlist']
        )
        processed_results = []

        for result in results.get("results", []):
            entry = f"### {result['title']}\n- URL: {result['url']}\n- Content: {result['content']}\n"
            processed_results.append(entry)
        
        return "\n---\n".join(processed_results)
    except Exception as e:
        return f"Search Error: {str(e)}"


#  유튜브 메타데이터, 스크립트 추출 도구
def get_video_id(url: str) -> str:
    """URL에서 Video ID 추출"""
    
    if "v=" in url:
        return url.split("v=")[1].split("&")[0]
    elif "youtu.be" in url:
        return url.split("/")[-1]
    return ""

def fetch_mestadata(video_id: str) -> Dict[str, Any]:
    """Youtube Data API v3를 이용한 메타데이터 수집"""

    YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")
    if not YOUTUBE_API_KEY:
        return {"title": "NO API key", "view_count": 0}

    try:
        youtube = build("youtube", "v3", developerKey=YOUTUBE_API_KEY)
        response = youtube.videos().list(
                    part="snippet, statistics",  # 더 확장 가능
                    id=video_id
                ).execute()
        print(f"response: {response}")
        item = response["items"][0]
        snippet = item["snippet"]
        stats = item["statistics"]

        return {
            "title": snippet["title"],
            "channel_title": snippet["channelTitle"],
            "published_at": snippet["publishedAt"],
            "view_count": stats.get("viewCount", 0),
            "like_count": stats.get("likeCount", 0),
            "comment_count": stats.get("commentCount", 0),
            } 
    except Exception as e:
        return {"error": f"error {e} occured", "view_count": 0}


def fetch_transcript_text(video_id: str) -> str:
    """YoutubeTranscript API를 통한 자막 추출"""
    try:
        transcript_list = YouTubeTranscriptApi().fetch(
        video_id=video_id,
        languages=['ko', 'en'])
        
        formatter = TextFormatter()
        return formatter.format_transcript(transcript_list)  # transcript
    except Exception as e:
        return ""

# 여기서의 인자는 어떻게 줄 수 있을까.... 그리고 어떤 형태인지 어디서 명시하지?
# 일단 폴더 하나라고 생각하자. 아니 의도한대로 되려면 날짜가 들어가야한다.
# 최종적으로는 workspace/날짜/~~_transcript.md
@tool
def get_youtube_transcript(video_url: str, save_dir: Optional[str] = None) -> str:
    """
    Extract metadata and transcripts of YouTube Video

    Args:
        video_url: video url to extract information
        save_dir: Optional directory path to save the transcript file.
                if provided, saves to '{save_dir}/{video_id}_transcript.md'.
                else, "{WORKSPACE_ROOT}/2024-05-21_14-30/{video_id}_transcript.md".
    Returns:
        Preview of information and write the full transcript at the specified path.
    """
    video_id = get_video_id(video_url)
    if not video_id:
        return "유효하지 않은 Youtube URL입니다."

    meta = fetch_mestadata(video_id)
    if "error" in meta:
        return f"API 오류: {meta['error']}\n(API Key를 확인하거나 할당량을 체크하세요.)"
    
    title = meta.get("title", f"Video {video_id}")

    full_transcript = fetch_transcript_text(video_id)
    if not full_transcript:
        return f"'{title}' 영상에서 자막을 찾을 수 없습니다."
    
    save_filename = f"{video_id}_transcript.md"
    
    
    if save_dir:  # 있다면
        directory = (WORKSPACE_ROOT / save_dir).resolve()  # resolve 큰 차이 현재 없음
    else:
        directory = WORKSPACE_ROOT
    print(f"directory: {directory}")

    try:
        directory.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        return f"Error creating directory {directory}: {str(e)}"
    
    file_path = directory / save_filename
    file_content = f"""# {title}
- **Channel**: {meta.get('channel_title')}
- **Views**: {meta.get('view_count')}
- **Published**: {meta.get('published_at')}
- **URL**: {video_url}

## Transcript
{full_transcript}
"""
    print(file_path)
    with open(file=file_path, mode='w', encoding='utf-8-sig') as f:
        f.write(file_content)
    
    preview = file_content[:500].replace("\n", " ")
    return f"""
[분석 완료] (Repo Style)
- **영상** {title}
- **채널** {meta.get('channel_title')}
- **저장 위치** '{file_path}' (내용은 'read_file'로 확인)
- **미리보기** {preview}..
"""

# 누가 읽냐에 따라 file_path는 달라져야함.
# tool에는 prompt에서 작성된 인자를 통해, tool calling이 이루어지도록 만들어야 함. 
# Analyst(Youtube)의 경우에는 transcript를, Writer의 경우에는 summary를 읽어야 함
# Analyst `save_dir` argument to: `research_workspace/{current_time}/transcripts`

@tool
def read_local_file(file_path: str, file_name: str) -> str:
    """
    Read the content of a local file.
    Use this to read transcripts or summaries using paths provided by other tools.
    
    Args:
        file_path: The path to the file to read.
        file_name: The name of the file to read(e.g.: gwgVVhwzXMg_{category}.md). category would be `transcript` or `summary`
    """
    try:
        p = Path(file_path)
        print(f"read_local_file: {p}")

        if not p.is_absolute():
            full_path = (WORKSPACE_ROOT / p).resolve()
        else:
            full_path = p.resolve()
        
        file = full_path / file_name
        if not file.exists():
            return f"Error: File not found at {full_path} / {file_name}. Please check if the path is correct."

        with open(file, "r", encoding="utf-8") as f:
            return f.read()
        
    except Exception as e:
        return f"Error reading file: {str(e)}"
    

# 누가 읽냐에 따라 file_path는 달라져야함.
# Analyst(Youtube)의 경우에는 summary를, Writer의 경우에는 final_report를 작성해야 함
@tool
def write_local_file(file_path: str, content: str, category: Optional[str]='summary') -> str:
    """
    Write content to a local file.
    
    Args:
        file_path: The path where the file should be saved.
        content: The text content to write.
        category: (Optional) The category of the file (if exist, summary or final_report)
    """
    try:
        p = Path(file_path)
        if not p.is_absolute():
            full_path = (WORKSPACE_ROOT / p).resolve()
        else:
            full_path = p.resolve()
        
        full_path.parent.mkdir(parents=True, exist_ok=True)  # ensure

        with open(full_path, "w", encoding="utf-8-sig") as f:
            f.write(content)
        return f"Successfully wrote to {full_path}"
    except Exception as e:
        return f"Error writing file: {str(e)}"