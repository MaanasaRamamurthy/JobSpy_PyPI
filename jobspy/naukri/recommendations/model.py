from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RecommendationRequest:
    cluster_id: str
    page_number: int | None = None

    def to_payload(self) -> dict[str, str | int]:
        payload: dict[str, str | int] = {
            "clusterId": self.cluster_id,
            "src": "recommClusterApi",
        }
        if self.page_number is not None:
            payload["pageNo"] = self.page_number
        return payload
