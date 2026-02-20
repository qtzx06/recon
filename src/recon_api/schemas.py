from typing import Any

from pydantic import BaseModel, Field


class WalletReportRequest(BaseModel):
    wallet: str = Field(..., description='Target Solana wallet address')
    max_signatures: int | None = Field(
        default=None,
        ge=5,
        le=500,
        description='Override signature fetch limit for this request',
    )


class WalletMetrics(BaseModel):
    wallet: str
    signature_count: int
    total_fees_sol: float
    inbound_sol: float
    outbound_sol: float
    transfer_volume_sol: float
    net_flow_sol: float
    active_days: int
    top_counterparties: list[dict[str, Any]]


class WalletFundingEdge(BaseModel):
    wallet: str
    total_sol: float
    transfers: int


class WalletProgramUsage(BaseModel):
    program: str
    interactions: int


class WalletIntelligence(BaseModel):
    first_seen_at: str | None = None
    last_seen_at: str | None = None
    unique_counterparties: int
    likely_funders: list[WalletFundingEdge]
    likely_funded_wallets: list[WalletFundingEdge]
    frequent_programs: list[WalletProgramUsage]
    linked_wallets: list[str]


class SocialMention(BaseModel):
    username: str | None = None
    name: str | None = None
    text: str
    created_at: str | None = None
    url: str | None = None


class SocialIntel(BaseModel):
    query_terms: list[str]
    total_results: int
    mentions: list[SocialMention]


class TraceStep(BaseModel):
    step: str
    duration_ms: int
    ok: bool
    detail: str | None = None


class WalletReportResponse(BaseModel):
    metrics: WalletMetrics
    intelligence: WalletIntelligence | None = None
    social: SocialIntel | None = None
    analysis: str
    model: str | None = None
    trace: list[TraceStep] = Field(default_factory=list)
