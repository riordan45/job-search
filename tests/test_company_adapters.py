from __future__ import annotations

from job_search.adapters.amazon import _country_from_item, _detail_url as amazon_detail_url, _location_text
from job_search.adapters.apple import _detail_url as apple_detail_url
from job_search.adapters.workday import _country_facet_ids
from job_search.enums import Country


def test_apple_detail_url_uses_slug_when_present() -> None:
    assert apple_detail_url("114438158", "us-specialist") == "https://jobs.apple.com/en-us/details/114438158/us-specialist"


def test_amazon_detail_url_uses_official_path() -> None:
    item = {"job_path": "/en/jobs/3092179/software-engineer"}
    assert amazon_detail_url(item) == "https://www.amazon.jobs/en/jobs/3092179/software-engineer"


def test_amazon_location_text_prefers_structured_locations() -> None:
    item = {
        "location": "DE, BE, Berlin",
        "locations": [
            '{"normalizedStateName":"Berlin","normalizedCountryName":"Germany","city":"Berlin"}',
            '{"normalizedStateName":"Berlin","normalizedCountryName":"Germany","city":"Berlin"}',
            '{"normalizedStateName":"Zurich","normalizedCountryName":"Switzerland","city":"Zurich"}',
        ],
    }
    assert _location_text(item) == "Berlin, Germany | Zurich, Switzerland"


def test_amazon_country_mapping_prefers_official_iso3_code() -> None:
    item = {"country_code": "ROU"}
    country = _country_from_item(item, "Iasi, Romania", default="DE")
    assert country == Country.RO


def test_workday_country_facet_ids_extract_target_ids() -> None:
    payload = {
        "facets": [
            {
                "facetParameter": "locationMainGroup",
                "values": [
                    {
                        "facetParameter": "locationHierarchy1",
                        "values": [
                            {"descriptor": "Germany", "id": "de-id"},
                            {"descriptor": "Netherlands", "id": "nl-id"},
                            {"descriptor": "United States", "id": "us-id"},
                        ],
                    }
                ],
            }
        ]
    }
    assert _country_facet_ids(payload, ["Germany", "Netherlands"]) == ["de-id", "nl-id"]
