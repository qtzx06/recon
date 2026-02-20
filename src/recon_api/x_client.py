from typing import Any
from urllib.parse import unquote

import httpx

from .schemas import SocialIntel, SocialMention


def search_x_mentions(
    bearer_token: str, query_terms: list[str], timeout_s: int, max_results: int = 10
) -> SocialIntel:
    token = unquote(bearer_token.strip())
    terms = [t for t in query_terms if t]
    if not terms:
        return SocialIntel(query_terms=[], total_results=0, mentions=[])

    query = ' OR '.join(f'"{term}"' for term in terms[:5])
    headers = {'Authorization': f'Bearer {token}'}
    params = {
        'query': query,
        'max_results': max(10, min(max_results, 100)),
        'tweet.fields': 'created_at,author_id',
        'expansions': 'author_id',
        'user.fields': 'username,name',
    }

    with httpx.Client(timeout=timeout_s) as client:
        resp = client.get('https://api.x.com/2/tweets/search/recent', headers=headers, params=params)
        resp.raise_for_status()
        payload: dict[str, Any] = resp.json()

    user_by_id: dict[str, dict[str, Any]] = {}
    includes = payload.get('includes', {})
    for user in includes.get('users', []):
        uid = user.get('id')
        if uid:
            user_by_id[uid] = user

    mentions: list[SocialMention] = []
    for tweet in payload.get('data', [])[:max_results]:
        uid = tweet.get('author_id')
        user = user_by_id.get(uid, {})
        username = user.get('username')
        mentions.append(
            SocialMention(
                username=username,
                name=user.get('name'),
                text=tweet.get('text', ''),
                created_at=tweet.get('created_at'),
                url=f'https://x.com/{username}/status/{tweet.get("id")}' if username else None,
            )
        )

    return SocialIntel(query_terms=terms[:5], total_results=len(mentions), mentions=mentions)
