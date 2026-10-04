from pydantic import BaseModel


class Finding(BaseModel):
    tool: str
    rule_id: str
    severity: str
    message: str
    file: str
    line: int
    cwe: list[str] = []
    end_line: int | None = None
