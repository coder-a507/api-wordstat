import json
import logging
import os
import time
from typing import List, Optional

import requests
from dotenv import load_dotenv

from app.nlp import extract_word_stats

load_dotenv()

POLL_INTERVAL_SECONDS = 5
REQUEST_TIMEOUT_SECONDS = 10

logger = logging.getLogger(__name__)


def _required_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"{name} is not set")
    return value


def claim_job(session: requests.Session, base_url: str, token: str) -> Optional[dict]:
    response = session.get(
        base_url,
        params={"action": "claim"},
        headers={"X-Service-Token": token},
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    body = response.json()
    if body["id"] is None:
        return None
    return body


def complete_job(
    session: requests.Session,
    base_url: str,
    token: str,
    job_id: int,
    result: List[dict],
) -> None:
    response = session.post(
        base_url,
        params={"action": "complete"},
        headers={"X-Service-Token": token},
        data={"id": job_id, "json": json.dumps(result)},
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    if response.status_code == 409:
        logger.info("job %s no longer claimable, skipping", job_id)
        return
    response.raise_for_status()


def fail_job(
    session: requests.Session,
    base_url: str,
    token: str,
    job_id: int,
    message: str,
) -> None:
    response = session.post(
        base_url,
        params={"action": "fail"},
        headers={"X-Service-Token": token},
        data={"id": job_id, "message": message},
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()


def poll_once(session: requests.Session, base_url: str, token: str) -> bool:
    try:
        job = claim_job(session, base_url, token)
    except requests.exceptions.RequestException as exc:
        logger.error("claim failed: %s", exc)
        return False

    if job is None:
        return False

    try:
        result = extract_word_stats(job["txt"])
    except Exception as exc:
        try:
            fail_job(session, base_url, token, job["id"], str(exc))
        except requests.exceptions.RequestException as report_exc:
            logger.error("fail report failed for job %s: %s", job["id"], report_exc)
        return True

    try:
        complete_job(session, base_url, token, job["id"], result)
    except requests.exceptions.RequestException as exc:
        logger.error("complete report failed for job %s: %s", job["id"], exc)
    return True


def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    base_url = _required_env("WORD_STATS_SERVICE_URL")
    token = _required_env("WORD_STATS_SERVICE_TOKEN")
    session = requests.Session()
    logger.info(
        "worker started, polling %s every %ss", base_url, POLL_INTERVAL_SECONDS
    )
    while True:
        try:
            handled = poll_once(session, base_url, token)
            if not handled:
                time.sleep(POLL_INTERVAL_SECONDS)
        except KeyboardInterrupt:
            logger.info("worker stopped")
            break


if __name__ == "__main__":
    main()
