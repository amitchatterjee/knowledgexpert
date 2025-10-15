from typing import Optional
from pydantic import BaseModel, Field

class AnalystOutput(BaseModel):
    summary: str = Field(description="Summary of the analyst's response")
    classification: str = Field(description="Classification of the request")
    codeGenerationRequirements: str = Field(description="Rule code generation requirements, if applicable")
    ruleset: str = Field(description="Ruleset name")
    configGenerationRequirements: str = Field(description="Configuration generation requirements, if applicable")
    testGenerationRequirements: str = Field(description="Test case generation requirements, if applicable")
    analysis: str = Field(description="Details of the analysis")
    references: Optional[list[str]] = Field(description="References used to create the analysis")

    def __str__(self):
        fields = []
        for field, value in self.__dict__.items():
            if value is not None and value != "" and value != []:
                fields.append(f"{field}:\n{value}")
        return f"{'\n\n'.join(fields)}"

class CodingOutput(BaseModel):
    summary: Optional[str] = Field(default=None, description="A one-line summary of the code snippet")
    description: Optional[str] = Field(default=None,
        description="Description of the code snippet")
    code: str = Field(description="A Python code for the rule")
    fileName: str = Field(description="Python file name. Don't include module name")
    ruleName: str = Field(description="Python function name for this rule")
    explanation: Optional[str] = Field(default=None, 
        description="Detailed explanation of the code")
    references: Optional[list[str]] = Field(default=None,
        description="A list of URLs containing more information")
    
    def __str__(self):
        fields = []
        for field, value in self.__dict__.items():
            if value is not None and value != "" and value != []:
                fields.append(f"{field}:\n{value}")
        return f"{'\n\n'.join(fields)}"

class TestFileOutput(BaseModel):
    fileName: str = Field(description="CSV file name")
    content: str = Field(description="CSV content")

class TestingOutput(BaseModel):
    summary: Optional[str] = Field("A one-line summary of the generated test data")
    description: Optional[str] = Field(
        description="Description of the test data")
    content: list[TestFileOutput] = Field("Test data")
    explanation: Optional[str] = Field(
        description="Detailed explanation of the tests")
    references: Optional[list[str]] = Field(
        description="A list of URLs containing more information")
    
    def __str__(self):
        fields = []
        for field, value in self.__dict__.items():
            if field == 'content':
                buffer = ''
                for element in value:
                    buffer = buffer + f"\n{element.fileName}:\n{element.content}"
                fields.append(f"{field}:\n{buffer}")
            elif value is not None and value != "" and value != []:
                fields.append(f"{field}:\n{value}")
            
        return f"{'\n\n'.join(fields)}"


class CodingAdvice(BaseModel):
    summary: Optional[str] = Field(default=None, description="A one-line summary of the code snippet")
    description: Optional[str] = Field(default=None, description="Description of the code snippet")
    code: str = Field(description="A Python Code Snippet")
    explanation: Optional[str] = Field(default=None, description="Detailed explanation of the code")
    references: Optional[list[str]] = Field(default=None, description="A list of URLs containing more information")

    def __str__(self):
        fields = []
        for field, value in self.__dict__.items():
            if value is not None and value != "" and value != []:
                fields.append(f"{field}:\n{value}")
        return f"{'\n\n'.join(fields)}"

class BookWormOutput(BaseModel):
    informationFound: bool = Field(default=False, description="True if relevant information is found for this document segment")
    summary: Optional[str] = Field(default=None, description="A one-line summary of the findings")
    explanation: Optional[str] = Field(default=None, 
        description="Detailed explanation of the findings")
    references: Optional[list[str]] = Field(default=None,
        description="A list of URLs containing the sources from where the findings were derived")
    def __str__(self):
        fields = []
        for field, value in self.__dict__.items():
            if value is not None and value != "" and value != []:
                fields.append(f"{field}:\n{value}")
        return f"{'\n\n'.join(fields)}"
