from __future__ import annotations

from dataclasses import dataclass, field
import os
import ssl
import urllib.error
import urllib.request


@dataclass
class FlagDownloadResult:
    downloaded: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)
    failures_detail: dict[str, str] = field(default_factory=dict)


def _candidate_urls(code: str) -> list[str]:
    return [
        f"https://raw.githubusercontent.com/ashleedawg/flags/master/{code}.png",
        f"https://raw.githubusercontent.com/ashleedawg/flags/master/{code.lower()}.png",
        f"https://raw.githubusercontent.com/ashleedawg/flags/main/{code}.png",
        f"https://raw.githubusercontent.com/ashleedawg/flags/main/{code.lower()}.png",
    ]


def download_flags(codes: list[str], cache_dir: str, timeout_sec: float = 15.0) -> FlagDownloadResult:
    os.makedirs(cache_dir, exist_ok=True)
    result = FlagDownloadResult()
    ssl_ctx = ssl.create_default_context()

    seen: set[str] = set()
    for raw in codes:
        code = (raw or "").strip().upper()
        if not code or code in seen:
            continue
        seen.add(code)

        target = os.path.join(cache_dir, f"{code.lower()}.png")
        last_error = "not found"
        ok = False
        for url in _candidate_urls(code):
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "tennis-match-condenser/1.7"})
                with urllib.request.urlopen(req, timeout=timeout_sec, context=ssl_ctx) as response:
                    payload = response.read()
                if not payload:
                    raise RuntimeError("empty file")
                with open(target, "wb") as out:
                    out.write(payload)
                result.downloaded.append(code)
                ok = True
                break
            except urllib.error.HTTPError as exc:
                last_error = f"HTTP {exc.code}"
            except urllib.error.URLError as exc:
                last_error = f"network {exc.reason}"
            except ssl.SSLError as exc:
                last_error = f"ssl {exc}"
            except (TimeoutError, OSError, RuntimeError) as exc:
                last_error = str(exc)
        if not ok:
            result.failed.append(code)
            result.failures_detail[code] = last_error

    return result
