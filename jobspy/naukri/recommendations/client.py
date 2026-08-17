from __future__ import annotations

import requests

from jobspy.naukri.config import RECOMMENDED_JOBS_API_URL
from jobspy.naukri.constant import recommendation_headers
from jobspy.naukri.recommendations.model import RecommendationRequest


class RecommendationRequestError(RuntimeError):
    """Raised when Naukri returns an unusable recommendation response."""


class NaukriRecommendationClient:
    def __init__(self, session: requests.Session) -> None:
        self.session = session
        self.headers = {
            **recommendation_headers,
            "nkparam": None,
        }

    def fetch_cluster(self, cluster_id: str, max_jobs: int) -> list[dict]:
        data = self._fetch_cluster_page(cluster_id)
        jobs = data["jobDetails"]
        expected_count = data.get("noOfJobs")
        if not isinstance(expected_count, int):
            expected_count = len(jobs)

        collected_ids = {
            str(job.get("jobId"))
            for job in jobs
            if job.get("jobId") is not None
        }
        page_number = 2

        while len(jobs) < min(expected_count, max_jobs):
            page_data = self._fetch_cluster_page(
                cluster_id,
                page_number=page_number,
            )
            page_jobs = page_data["jobDetails"]
            if not page_jobs:
                break

            new_jobs = []
            for job in page_jobs:
                job_id = str(job.get("jobId") or "")
                if job_id and job_id in collected_ids:
                    continue
                if job_id:
                    collected_ids.add(job_id)
                new_jobs.append(job)

            if not new_jobs:
                break

            jobs.extend(new_jobs)
            page_number += 1

        return jobs[:max_jobs]

    def fetch_all(
        self,
        cluster_ids: tuple[str, ...],
        max_jobs: int,
    ) -> list[dict]:
        jobs_by_id: dict[str, dict] = {}

        for cluster_id in cluster_ids:
            for raw_job in self.fetch_cluster(cluster_id, max_jobs):
                job_id = str(raw_job.get("jobId") or "")
                if not job_id:
                    continue

                if job_id not in jobs_by_id:
                    normalized_job = dict(raw_job)
                    normalized_job["recommendationClusters"] = [cluster_id]
                    jobs_by_id[job_id] = normalized_job
                else:
                    clusters = jobs_by_id[job_id]["recommendationClusters"]
                    if cluster_id not in clusters:
                        clusters.append(cluster_id)

        return list(jobs_by_id.values())[:max_jobs]

    def _fetch_cluster_page(
        self,
        cluster_id: str,
        *,
        page_number: int | None = None,
    ) -> dict:
        request = RecommendationRequest(
            cluster_id=cluster_id,
            page_number=page_number,
        )
        response = self.session.post(
            RECOMMENDED_JOBS_API_URL,
            headers=self.headers,
            json=request.to_payload(),
            timeout=30,
        )
        if response.status_code != 200:
            preview = response.text[:300].replace("\n", " ")
            raise RecommendationRequestError(
                "Naukri recommendation request failed for "
                f"cluster={cluster_id!r} with HTTP {response.status_code}: "
                f"{preview}"
            )

        try:
            data = response.json()
        except ValueError as exc:
            raise RecommendationRequestError(
                "Naukri returned non-JSON recommendations for "
                f"cluster={cluster_id!r}."
            ) from exc

        jobs = data.get("jobDetails")
        if not isinstance(jobs, list):
            raise RecommendationRequestError(
                "Naukri recommendation response for "
                f"cluster={cluster_id!r} does not contain a jobDetails list."
            )
        return data
