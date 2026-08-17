from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Any


WORK_MODE_MAP = {
    "office": "1",
    "remote": "2",
    "hybrid": "3",
}

CITY_GID_MAP = {
    "chennai": "183",
    "bengaluru": "97",
    "bangalore": "97",
    "hyderabad": "17",
    "pune": "139",
    "noida": "220",
}

SORT_MAP = {
    "relevance": "r",
    "date": "f",
    "recommended": "p",
}


@dataclass(slots=True)
class NaukriSearchParams:
    flow: str = "search"
    recommendation_clusters: list[str] | str = field(default_factory=list)
    sort_by: str = "relevance"
    freshness: int | str | None = None
    work_mode: list[str] | str = field(default_factory=list)
    experience: str | int | None = None
    salary_range: list[str] | str = field(default_factory=list)
    cities: list[str] | str = field(default_factory=list)
    city_type_gids: list[str] | str = field(default_factory=list)
    department: list[str] | str = field(default_factory=list)
    company_type: list[str] | str = field(default_factory=list)
    role_category: list[str] | str = field(default_factory=list)
    industry: list[str] | str = field(default_factory=list)
    posted_by: list[str] | str = field(default_factory=list)
    top_companies: list[str] | str = field(default_factory=list)
    ug_course: list[str] | str = field(default_factory=list)
    pg_course: list[str] | str = field(default_factory=list)
    stipend: list[str] | str = field(default_factory=list)
    duration: list[str] | str = field(default_factory=list)
    fetch_description: bool | None = None

    @classmethod
    def from_dict(cls, values: dict[str, Any] | None) -> NaukriSearchParams:
        values = values or {}
        flow = str(values.get("flow", "search")).strip().lower()
        if flow not in {"search", "recommended"}:
            raise ValueError(
                "Unsupported Naukri flow. Valid values: search, recommended."
            )
        if flow == "recommended":
            allowed = {"flow", "recommendation_clusters", "fetch_description"}
            unsupported = sorted(set(values) - allowed)
            if unsupported:
                raise ValueError(
                    "Naukri recommended flow does not support: "
                    f"{', '.join(unsupported)}."
                )
        try:
            params = cls(**values)
        except TypeError as exc:
            raise ValueError(f"Invalid Naukri search parameter: {exc}") from exc
        params.flow = flow
        return params

    def get_recommendation_clusters(
        self,
        default_clusters: tuple[str, ...],
    ) -> tuple[str, ...]:
        clusters = _as_list(self.recommendation_clusters)
        if not clusters:
            clusters = list(default_clusters)
        if any(not cluster.strip() for cluster in clusters):
            raise ValueError("Naukri recommendation clusters cannot be empty.")
        return tuple(dict.fromkeys(cluster.strip() for cluster in clusters))

    def to_api_params(
        self,
        *,
        page: int,
        keyword: str,
        results_per_page: int,
        location: str | None,
        hours_old: int | None,
        is_remote: bool,
    ) -> dict[str, Any]:
        cities = _as_list(self.cities)
        explicit_cities = bool(cities)
        city_type_gids = _as_list(self.city_type_gids)

        if not cities and not city_type_gids and location:
            cities = [location.split(",", 1)[0].strip()]

        mapped_city_gids, unsupported_cities = _map_city_gids(cities)
        if explicit_cities and unsupported_cities:
            supported = ", ".join(sorted(CITY_GID_MAP))
            unsupported = ", ".join(unsupported_cities)
            raise ValueError(
                f"Unsupported Naukri cities: {unsupported}. Supported values: "
                f"{supported}. Use city_type_gids for other cities."
            )

        for city_gid in mapped_city_gids:
            if city_gid not in city_type_gids:
                city_type_gids.append(city_gid)

        freshness = _normalize_freshness(self.freshness, hours_old)
        work_modes = _as_list(self.work_mode)
        if not work_modes and is_remote:
            work_modes = ["remote"]
        work_mode_ids = _map_work_modes(work_modes)

        sort_by = self.sort_by.strip().lower()
        if sort_by not in SORT_MAP:
            valid = ", ".join(SORT_MAP)
            raise ValueError(
                f"Unsupported Naukri sort_by: {self.sort_by!r}. Valid values: {valid}."
            )

        has_cluster_filters = any(
            [city_type_gids, work_mode_ids, self.salary_range, freshness]
        )
        params: dict[str, Any] = {
            "noOfResults": results_per_page,
            "urlType": "search_by_keyword",
            "searchType": "adv",
            "pageNo": page,
            "src": "cluster" if has_cluster_filters else "jobsearchDesk",
            "keyword": keyword,
            "k": keyword,
            "sort": SORT_MAP[sort_by],
        }

        if city_type_gids:
            params["nignbevent_src"] = "jobsearchDeskGNB"
            params["cityTypeGid"] = city_type_gids
        elif location:
            params["location"] = location

        if freshness:
            params["jobAge"] = freshness
        if work_mode_ids:
            params["wfhType"] = work_mode_ids
        if self.experience not in (None, ""):
            params["experience"] = str(self.experience)

        list_param_map = {
            "salary_range": "ctcFilter",
            "department": "jt",
            "company_type": "companyType",
            "role_category": "rCatId",
            "industry": "industryId",
            "posted_by": "atype",
            "top_companies": "topGid",
            "ug_course": "ugType",
            "pg_course": "pgType",
            "stipend": "stipend",
            "duration": "dur",
        }
        for field_name, api_name in list_param_map.items():
            values = _as_list(getattr(self, field_name))
            if field_name == "salary_range":
                values = [_map_salary_range(value) for value in values]
            if values:
                params[api_name] = values

        return params


def _as_list(value: Any) -> list[str]:
    if value in (None, ""):
        return []
    if isinstance(value, (list, tuple, set)):
        return [str(item) for item in value if item not in (None, "")]
    if isinstance(value, str) and "," in value:
        return [item.strip() for item in value.split(",") if item.strip()]
    return [str(value)]


def _map_city_gids(cities: list[str]) -> tuple[list[str], list[str]]:
    city_gids = []
    unsupported_cities = []
    for city in cities:
        city_gid = CITY_GID_MAP.get(city.strip().lower())
        if city_gid is None:
            unsupported_cities.append(city)
        elif city_gid not in city_gids:
            city_gids.append(city_gid)
    return city_gids, unsupported_cities


def _map_work_modes(work_modes: list[str]) -> list[str]:
    work_mode_ids = []
    unsupported_modes = []
    for work_mode in work_modes:
        work_mode_id = WORK_MODE_MAP.get(work_mode.strip().lower())
        if work_mode_id is None:
            unsupported_modes.append(work_mode)
        elif work_mode_id not in work_mode_ids:
            work_mode_ids.append(work_mode_id)
    if unsupported_modes:
        valid = ", ".join(WORK_MODE_MAP)
        unsupported = ", ".join(unsupported_modes)
        raise ValueError(
            f"Unsupported Naukri work modes: {unsupported}. Valid values: {valid}."
        )
    return work_mode_ids


def _normalize_freshness(
    freshness: int | str | None,
    hours_old: int | None,
) -> str | None:
    if freshness is None and hours_old:
        return str(math.ceil(hours_old / 24))
    if freshness in (None, "", "all"):
        return None
    try:
        days = int(freshness)
    except (TypeError, ValueError) as exc:
        raise ValueError("Naukri freshness must be a positive number of days.") from exc
    if days < 1:
        raise ValueError("Naukri freshness must be a positive number of days.")
    return str(days)


def _map_salary_range(value: str) -> str:
    normalized = value.strip().lower()
    normalized = re.sub(r"\s*lakhs?\s*", "", normalized)
    normalized = re.sub(r"\s*(?:-|to)\s*", "to", normalized)
    if re.fullmatch(r"\d+to\d+", normalized):
        return normalized
    raise ValueError(
        f"Unsupported Naukri salary range: {value!r}. Use a range such as '10-15'."
    )
