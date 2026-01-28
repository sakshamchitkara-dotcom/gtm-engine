from dataclasses import dataclass, field, asdict


@dataclass
class Lead:
    email: str
    first_name: str = ""
    last_name: str = ""
    title: str = ""
    company: str = ""
    employees: int = 0
    industry: str = ""
    country: str = ""
    source: str = ""
    # filled in by the pipeline
    domain: str = ""
    seniority: str = ""
    size_band: str = ""
    is_free_email: bool = False
    email_status: str = ""
    score: int = 0
    tier: str = ""
    owner: str = ""
    stage: str = "new"
    reasons: list = field(default_factory=list)

    def to_dict(self):
        return asdict(self)
