from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8', extra='ignore')

    aws_region: str = Field(default='us-west-2', alias='AWS_REGION')
    aws_access_key_id: str | None = Field(default=None, alias='AWS_ACCESS_KEY_ID')
    aws_secret_access_key: str | None = Field(default=None, alias='AWS_SECRET_ACCESS_KEY')
    aws_session_token: str | None = Field(default=None, alias='AWS_SESSION_TOKEN')
    bedrock_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices('BEDROCK_API_KEY', 'AWS_BEARER_TOKEN_BEDROCK'),
    )
    bedrock_model_id: str = Field(
        default='anthropic.claude-3-5-sonnet-20241022-v2:0', alias='BEDROCK_MODEL_ID'
    )
    solana_rpc_url: str = Field(default='https://api.mainnet-beta.solana.com', alias='SOLANA_RPC_URL')
    solana_signature_limit: int = Field(default=50, alias='SOLANA_SIGNATURE_LIMIT')
    recon_timeout_seconds: int = Field(default=25, alias='RECON_TIMEOUT_SECONDS')
    recon_metrics_only: bool = Field(default=False, alias='RECON_METRICS_ONLY')
    x_bearer_token: str | None = Field(default=None, alias='X_BEARER_TOKEN')
    x_max_results: int = Field(default=10, alias='X_MAX_RESULTS')
    recon_enable_x_search: bool = Field(default=False, alias='RECON_ENABLE_X_SEARCH')
    dd_api_key: str | None = Field(default=None, alias='DD_API_KEY')
    dd_service: str = Field(default='recon-api', alias='DD_SERVICE')
    dd_env: str = Field(default='dev', alias='DD_ENV')
    dd_version: str = Field(default='0.1.0', alias='DD_VERSION')
    dd_site: str = Field(default='datadoghq.com', alias='DD_SITE')
    dd_send_logs: bool = Field(default=True, alias='DD_SEND_LOGS')
    dd_trace_enabled: bool = Field(default=False, alias='DD_TRACE_ENABLED')
    dd_trace_agent_url: str | None = Field(default=None, alias='DD_TRACE_AGENT_URL')


settings = Settings()
