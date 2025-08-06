from typing import Optional
from pydantic import BaseModel, Field

class AnalystOutput(BaseModel):
    summary: str
    classification: str
    codeGenRequirements: str
    configGenRequirements: str
    testGenRequirements: str
    analysis: str
    references: Optional[list]

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
    references: Optional[list] = Field(
        description="A list of URLs containing more information")
    
    def __str__(self):
        fields = []
        for field, value in self.__dict__.items():
            if value is not None and value != "" and value != []:
                fields.append(f"{field}:\n{value}")
        return f"{'\n\n'.join(fields)}"

class CodingAdvice(BaseModel):
    summary: Optional[str] = Field("A one-line summary of the code snippet")
    description: Optional[str] = Field(
        description="Description of the code snippet")
    code: str = Field(description="A Python Code Snippet")
    explanation: Optional[str] = Field(
        description="Detailed explanation of the code")
    references: Optional[list] = Field(
        description="A list of URLs containing more information")

    def __str__(self):
        fields = []
        for field, value in self.__dict__.items():
            if value is not None and value != "" and value != []:
                fields.append(f"{field}:\n{value}")
        return f"{'\n\n'.join(fields)}"
