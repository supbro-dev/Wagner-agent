from typing import Optional, Dict, Any

import requests

from config import Config


def http_get_old(
        url: str,
        params: Dict[str, Any] | None = None,
        timeout: int = 10,
        **kwargs
) -> Dict[str, Any]:
    if Config.WAGNER_API_ENDPOINT not in url:
        url = Config.WAGNER_API_ENDPOINT + url

    print("HTTP_GET:", url)

    response = requests.get(
        url=url,
        params=params,
        headers={"Content-Type": "application/json"},
        timeout=timeout,
        **kwargs
    )

    response.raise_for_status()
    return response.json()

def http_get(
        url: str,
        params: Dict[str, Any] | None = None,
        timeout: int = 10,
        **kwargs
) -> Dict[str, Any]:
    print("HTTP_GET:", url)

    response = requests.get(
        url=url,
        params=params,
        headers={"Content-Type": "application/json"},
        timeout=timeout,
        **kwargs
    )

    response.raise_for_status()
    return response.json()

def http_post(
        url: str,
        params: Dict[str, Any] | None = None,
        timeout: int = 10,
        **kwargs
) -> Dict[str, Any]:
    print("HTTP_POST:", url)

    response = requests.post(
        url=url,
        json=params,  # 使用 json 参数发送 JSON 数据
        headers={"Content-Type": "application/json"},
        timeout=timeout,
        **kwargs
    )

    response.raise_for_status()
    return response.json()

