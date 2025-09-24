from typing import Optional
from pydantic import BaseModel, Field

class AnalystOutput(BaseModel):
    summary: str
    classification: str
    codeGenRequirements: str
    configGenRequirements: str
    testGenRequirements: str
    analysis: str
    references: Optional[list[str]]

    def __str__(self):
        fields = []
        for field, value in self.__dict__.items():
            if value is not None and value != "" and value != []:
                fields.append(f"{field}:\n{value}")
        return f"{'\n\n'.join(fields)}"

class CodingOutput(BaseModel):
    summary: Optional[str] = Field("A one-line summary of the code snippet")
    description: Optional[str] = Field(
        description="Description of the code snippet")
    code: str = Field(description="A Python Code Snippet")
    filename: str = Field(description="Python file name")
    explanation: Optional[str] = Field(
        description="Detailed explanation of the code")
    references: Optional[list[str]] = Field(
        description="A list of URLs containing more information")
    
    def __str__(self):
        fields = []
        for field, value in self.__dict__.items():
            if value is not None and value != "" and value != []:
                fields.append(f"{field}:\n{value}")
        return f"{'\n\n'.join(fields)}"

class TestFileOutout(BaseModel):
    filename: str = Field(description="CSV file name")
    content: str = Field(description="CSV content")

    def __str__(self):
        fields = []
        for field, value in self.__dict__.items():
            if value is not None and value != "" and value != []:
                fields.append(f"{field}:\n{value}")
        return f"{'\n\n'.join(fields)}"

class TestingOutput(BaseModel):
    summary: Optional[str] = Field("A one-line summary of the generated test data")
    description: Optional[str] = Field(
        description="Description of the test data")
    # data: str = Field(description="Test data")
    content: list[TestFileOutout] = Field("Test data")
    explanation: Optional[str] = Field(
        description="Detailed explanation of the tests")
    references: Optional[list[str]] = Field(
        description="A list of URLs containing more information")
    
    def __str__(self):
        fields = []
        for field, value in self.__dict__.items():
            if field == 'content':
                buffer = '['
                for i, element in enumerate(value):
                    buffer = buffer + f"\n[{i+1}]:\n{element}"
                buffer = buffer + '\n]'
                fields.append(f"{field}:\n{buffer}")
            elif value is not None and value != "" and value != []:
                fields.append(f"{field}:\n{value}")
            
        return f"{'\n\n'.join(fields)}"


class CodingAdvice(BaseModel):
    summary: Optional[str] = Field("A one-line summary of the code snippet")
    description: Optional[str] = Field(
        description="Description of the code snippet")
    code: str = Field(description="A Python Code Snippet")
    explanation: Optional[str] = Field(
        description="Detailed explanation of the code")
    references: Optional[list[str]] = Field(
        description="A list of URLs containing more information")

    def __str__(self):
        fields = []
        for field, value in self.__dict__.items():
            if value is not None and value != "" and value != []:
                fields.append(f"{field}:\n{value}")
        return f"{'\n\n'.join(fields)}"
