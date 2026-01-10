from pydantic import BaseModel, Field
from typing import List, Optional

# --- Math Tools ---

class AddInput(BaseModel):
    """Input model for addition."""
    a: int
    b: int

class AddOutput(BaseModel):
    """Output model for addition."""
    result: int

class SubtractInput(BaseModel):
    """Input model for subtraction."""
    a: int
    b: int

class SubtractOutput(BaseModel):
    """Output model for subtraction."""
    result: int

class MultiplyInput(BaseModel):
    """Input model for multiplication."""
    a: int
    b: int

class MultiplyOutput(BaseModel):
    """Output model for multiplication."""
    result: int

class SqrtInput(BaseModel):
    """Input model for square root calculation."""
    a: int
    b: int

class SqrtOutput(BaseModel):
    """Output model for square root calculation."""
    result: int

class DivideInput(BaseModel):
    """Input model for division."""
    a: int
    b: int

class DivideOutput(BaseModel):
    """Output model for division."""
    result: float

class PowerInput(BaseModel):
    """Input model for power calculation."""
    a: int
    b: int

class PowerOutput(BaseModel):
    """Output model for power calculation."""
    result: int

class CbrtInput(BaseModel):
    """Input model for cube root calculation."""
    a: int

class CbrtOutput(BaseModel):
    """Output model for cube root calculation."""
    result: float

class FactorialInput(BaseModel):
    """Input model for factorial calculation."""
    a: int

class FactorialOutput(BaseModel):
    """Output model for factorial calculation."""
    result: int

class RemainderInput(BaseModel):
    """Input model for remainder calculation."""
    a: int
    b: int

class RemainderOutput(BaseModel):
    """Output model for remainder calculation."""
    result: int

class SinInput(BaseModel):
    """Input model for sine calculation."""
    a: int

class SinOutput(BaseModel):
    """Output model for sine calculation."""
    result: float

class CosInput(BaseModel):
    """Input model for cosine calculation."""
    a: int

class CosOutput(BaseModel):
    """Output model for cosine calculation."""
    result: float

class TanInput(BaseModel):
    """Input model for tangent calculation."""
    a: int

class TanOutput(BaseModel):
    """Output model for tangent calculation."""
    result: float

class MineInput(BaseModel):
    """Input model for custom mine operation."""
    a: int
    b: int

class MineOutput(BaseModel):
    """Output model for custom mine operation."""
    result: int

# --- String & List Tools ---

class StringsToIntsInput(BaseModel):
    """Input model for converting a string to ASCII integers."""
    string: str

class StringsToIntsOutput(BaseModel):
    """Output model containing list of ASCII integers."""
    ascii_values: List[int]


class ExpSumInput(BaseModel):
    """Input model for exponential sum calculation."""
    numbers: List[int]

class ExpSumOutput(BaseModel):
    """Output model for exponential sum calculation."""
    result: float

class FibonacciInput(BaseModel):
    """Input model for Fibonacci sequence generation."""
    n: int

class FibonacciOutput(BaseModel):
    """Output model containing Fibonacci sequence."""
    result: List[int]

# --- Image Tools ---

class CreateThumbnailInput(BaseModel):
    """Input model for creating an image thumbnail."""
    image_path: str

class ImageOutput(BaseModel):
    """Output model containing image data."""
    data: bytes
    format: str

# --- Shell, Python, SQL Tools ---

class PythonCodeInput(BaseModel):
    """Input model for executing Python code."""
    code: str

class PythonCodeOutput(BaseModel):
    """Output model for Python code execution."""
    result: str

class ShellCommandInput(BaseModel):
    """Input model for executing a shell command."""
    command: str

# --- RAG and Extraction Tools ---

class UrlInput(BaseModel):
    """Input model containing a URL."""
    url: str

class URLListOutput(BaseModel):
    """Output model containing a list of URLs."""
    result: List[str]

class FilePathInput(BaseModel):
    """Input model containing a file path."""
    file_path: str

class MarkdownInput(BaseModel):
    """Input model containing markdown text."""
    text: str

class MarkdownOutput(BaseModel):
    """Output model containing markdown text."""
    markdown: str

class ChunkListOutput(BaseModel):
    """Output model containing a list of text chunks."""
    chunks: List[str]

# --- Memory Search ---

class SearchMemoryInput(BaseModel):
    """Input model for searching memory."""
    query: str

class EmptyInput(BaseModel):
    """Empty input model."""
    pass

# --- Search Tools ---

class SearchInput(BaseModel):
    """Input model for general search."""
    query: str
    max_results: int = Field(default=10, description="Maximum number of results to return")

class SearchDocumentsInput(BaseModel):
    """Input model for searching documents."""
    query: str

class UrlInput(BaseModel):
    """Input model containing a URL."""
    url: str

class FilePathInput(BaseModel):
    """Input model containing a file path."""
    file_path: str

class MarkdownOutput(BaseModel):
    """Output model containing markdown text."""
    markdown: str

class SummaryInput(BaseModel):
    """Input model for summarizing a URL."""
    url: str
    prompt: Optional[str] = None
