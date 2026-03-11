from __future__ import annotations

from job_search.adapters.asml import (
    _extract_job_payload as asml_extract_job_payload,
    _extract_sitemap_urls as asml_extract_sitemap_urls,
    _is_target_country as asml_is_target_country,
)
from job_search.adapters.ashby import _job_posting_url
from job_search.adapters.amazon import _country_from_item, _detail_url as amazon_detail_url, _location_text
from job_search.adapters.apple import _detail_url as apple_detail_url
from job_search.adapters.booking import _canonical_url as booking_canonical_url, _search_url as booking_search_url
from job_search.adapters.eightfold import _detail_api_url as eightfold_detail_api_url, _target_locations
from job_search.adapters.jane_street import _detail_url as jane_street_detail_url, _location_text as jane_street_location_text
from job_search.adapters.microsoft import _extract_listings, _location_url
from job_search.adapters.revolut import _extract_positions, _position_url
from job_search.adapters.spotify import _extract_job_payload as spotify_extract_job_payload, _target_locations as spotify_target_locations
from job_search.adapters.uber import _detail_url as uber_detail_url, _target_locations as uber_target_locations
from job_search.adapters.wise import _extract_job_posting, _location_from_path, _title_from_path
from job_search.adapters.workday import _country_facet_ids
from job_search.adapters.zalando import _extract_jobs, _job_url
from job_search.adapters.meta import _extract_job_posting as meta_extract_job_posting, _extract_lsd_token, _target_office_queries
from job_search.enums import Country


def test_asml_extract_sitemap_urls_reads_official_job_urls() -> None:
    xml = """
    <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
      <url><loc>https://www.asml.com/en/careers/find-your-job/senior-cloud-engineer-j00314603</loc></url>
      <url><loc>https://www.asml.com/en/careers/find-your-job/facility-management-services-spezialistin-j00910074</loc></url>
    </urlset>
    """
    assert asml_extract_sitemap_urls(xml) == [
        "https://www.asml.com/en/careers/find-your-job/senior-cloud-engineer-j00314603",
        "https://www.asml.com/en/careers/find-your-job/facility-management-services-spezialistin-j00910074",
    ]


def test_asml_extract_job_payload_reads_next_data() -> None:
    html = """
    <script id="__NEXT_DATA__" type="application/json">
    {"props":{"pageProps":{"jobData":{"id":"J-00910074","displayJobTitle":"Facility Management Services Spezialist:in","datePosted":"2026-02-06T00:00:00","location":"Berlin, Germany","city":"Berlin","country":"Germany","jobType":"Engineering","timeType":"Full time","remoteWork":"Hybrid","descriptionExternal":"<p>Build internal systems.</p>","detailPageUrl":"https://www.asml.com/en/careers/find-your-job/facility-management-services-spezialistin-j00910074"}}}}
    </script>
    """
    job = asml_extract_job_payload(html)
    assert job["id"] == "J-00910074"
    assert job["displayJobTitle"] == "Facility Management Services Spezialist:in"
    assert job["location"] == "Berlin, Germany"
    assert job["country"] == "Germany"


def test_asml_is_target_country_keeps_only_target_geographies() -> None:
    assert asml_is_target_country("Germany") is True
    assert asml_is_target_country("The Netherlands") is True
    assert asml_is_target_country("Romania") is True
    assert asml_is_target_country("Switzerland") is True
    assert asml_is_target_country("United States") is False


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


def test_jane_street_detail_url_uses_official_position_path() -> None:
    assert (
        jane_street_detail_url("8429265002")
        == "https://www.janestreet.com/join-jane-street/position/8429265002/"
    )


def test_jane_street_location_text_only_keeps_target_cities() -> None:
    assert jane_street_location_text({"city": "AMS"}) == "Amsterdam, Netherlands"
    assert jane_street_location_text({"city": "LDN"}) == ""


def test_eightfold_detail_api_url_uses_official_domain_and_position_id() -> None:
    assert (
        eightfold_detail_api_url("https://jobs.nvidia.com/careers", "nvidia.com", "893391009867")
        == "https://jobs.nvidia.com/api/pcsx/position_details?domain=nvidia.com&position_id=893391009867"
    )


def test_eightfold_detail_api_url_supports_microsoft_host() -> None:
    assert (
        eightfold_detail_api_url(
            "https://apply.careers.microsoft.com/careers",
            "microsoft.com",
            "1970393556643216",
        )
        == "https://apply.careers.microsoft.com/api/pcsx/position_details?domain=microsoft.com&position_id=1970393556643216"
    )


def test_eightfold_target_locations_keep_only_target_countries() -> None:
    item = {
        "locations": ["Switzerland, Zurich", "Poland, Warsaw", "Germany, Berlin"],
        "standardizedLocations": ["Zürich, ZH, CH", "Warsaw, Masovian Voivodeship, PL", "Berlin, Berlin, DE"],
    }
    assert _target_locations(item) == [
        "Switzerland, Zurich",
        "Germany, Berlin",
        "Zürich, ZH, CH",
        "Berlin, Berlin, DE",
    ]


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


def test_ashby_job_posting_url_uses_board_name_and_job_id() -> None:
    assert _job_posting_url("openai", "job-123") == "https://jobs.ashbyhq.com/openai/job/job-123"


def test_booking_search_url_uses_official_api_parameters() -> None:
    assert (
        booking_search_url("https://jobs.booking.com/booking/jobs/locations", "Romania", page=2, limit=10)
        == "https://jobs.booking.com/api/jobs?location=Romania&page=2&limit=10"
    )


def test_booking_canonical_url_prefers_public_canonical_link() -> None:
    item = {
        "meta_data": {"canonical_url": "https://www.bookingholdings-coe.com/bookingholdings-coe/jobs/27942?lang=en-us"},
        "apply_url": "https://careers-holdings-workingatbooking.icims.com/jobs/27942/login",
    }
    assert (
        booking_canonical_url(item)
        == "https://www.bookingholdings-coe.com/bookingholdings-coe/jobs/27942?lang=en-us"
    )


def test_revolut_position_url_uses_stable_id_route() -> None:
    assert (
        _position_url("7d3a7425-fe1a-456c-9dde-d19aba0cde88")
        == "https://www.revolut.com/en-RO/careers/position/7d3a7425-fe1a-456c-9dde-d19aba0cde88/"
    )


def test_revolut_extract_positions_reads_next_data_payload() -> None:
    html = """
    <script id="__NEXT_DATA__" type="application/json">
    {"props":{"pageProps":{"positions":[
      {
        "id":"7d3a7425-fe1a-456c-9dde-d19aba0cde88",
        "text":"Software Engineer (Python) - Mid/Senior",
        "team":"Engineering",
        "description":"",
        "video":null,
        "locations":[
          {"name":"Romania - Remote","type":"remote","country":"Romania"},
          {"name":"Poland - Remote","type":"remote","country":"Poland"}
        ]
      }
    ]}}}
    </script>
    """
    positions = _extract_positions(html)
    assert positions == [
        {
            "id": "7d3a7425-fe1a-456c-9dde-d19aba0cde88",
            "text": "Software Engineer (Python) - Mid/Senior",
            "team": "Engineering",
            "description": "",
            "video": None,
            "locations": [
                {"name": "Romania - Remote", "type": "remote", "country": "Romania"},
                {"name": "Poland - Remote", "type": "remote", "country": "Poland"},
            ],
        }
    ]


def test_uber_detail_url_uses_global_careers_path() -> None:
    assert uber_detail_url("156172") == "https://www.uber.com/global/en/careers/list/156172/"


def test_uber_target_locations_keep_only_target_countries() -> None:
    item = {
        "allLocations": [
            {"country": "NLD", "countryName": "Netherlands", "city": "Amsterdam"},
            {"country": "USA", "countryName": "United States", "region": "Washington", "city": "Seattle"},
            {"country": "CHE", "countryName": "Switzerland", "city": "Zurich"},
        ]
    }
    assert uber_target_locations(item) == ["Amsterdam, Netherlands", "Zurich, Switzerland"]


def test_microsoft_location_url_uses_official_location_page() -> None:
    assert (
        _location_url("amsterdam")
        == "https://careers.microsoft.com/v2/global/en/locations/amsterdam.html"
    )


def test_microsoft_extract_listings_parses_job_cards() -> None:
    html = """
    <a href="/v2/global/en/job/1843031/Senior-Software-Engineer">
      <h3>Senior Software Engineer</h3>
      <span>Location</span><span>Amsterdam, North Holland, Netherlands</span>
      <span>Profession</span><span>Software Engineering</span>
      <span>Work site</span><span>Up to 50% work from home</span>
      <span>Date posted</span><span>Mar 10, 2026</span>
    </a>
    <a href="/v2/global/en/job/1843032/Business-Manager">
      <h3>Business Manager</h3>
      <span>Location</span><span>Redmond, Washington, United States</span>
    </a>
    """
    listings = _extract_listings(html)

    assert listings == [
        {
            "external_id": "1843031",
            "title": "Senior Software Engineer",
            "url": "https://careers.microsoft.com/v2/global/en/job/1843031/Senior-Software-Engineer",
            "location_text": "Amsterdam, North Holland, Netherlands",
            "profession": "Software Engineering",
            "work_site": "Up to 50% work from home",
            "posted_at": listings[0]["posted_at"],
        }
    ]
    assert listings[0]["posted_at"] is not None


def test_wise_title_and_location_are_parsed_from_path() -> None:
    path = "/job/software-engineer-servicing-platform-in-amsterdam-jid-2636"
    assert _title_from_path(path) == "Software Engineer Servicing Platform"
    assert _location_from_path(path) == "Amsterdam"


def test_wise_extract_job_posting_reads_json_ld() -> None:
    html = """
    <script type="application/ld+json">
    {"@context":"http://schema.org","@type":"JobPosting","title":"Backend Engineer","datePosted":"2026-03-11T10:42:38+00:00","jobLocation":[{"@type":"Place","address":{"@type":"PostalAddress","addressLocality":"Amsterdam"}}]}
    </script>
    """
    posting = _extract_job_posting(html)
    assert posting["title"] == "Backend Engineer"
    assert posting["jobLocation"][0]["address"]["addressLocality"] == "Amsterdam"


def test_zalando_job_url_uses_official_path() -> None:
    assert (
        _job_url("2723255", "Senior Applied Scientist - CRM (All Genders)")
        == "https://jobs.zalando.com/en/jobs/2723255-Senior-Applied-Scientist---CRM-(All-Genders)"
    )


def test_zalando_extract_jobs_reads_embedded_payload() -> None:
    html = '28:{"data":[{"title":"Senior Applied Scientist - CRM (All Genders)","id":"2723255","entity":"Zalando SE","job_categories":["Applied Science & Research"],"offices":["Berlin"],"experience_level":"Professional Level","updated_at":"2026-03-11T01:46:50.200-07:00"}],"total":90}'
    jobs = _extract_jobs(html)
    assert jobs == [
        {
            "title": "Senior Applied Scientist - CRM (All Genders)",
            "id": "2723255",
            "entity": "Zalando SE",
            "job_categories": ["Applied Science & Research"],
            "offices": ["Berlin"],
            "experience_level": "Professional Level",
            "updated_at": "2026-03-11T01:46:50.200-07:00",
        }
    ]


def test_meta_extract_lsd_token_reads_page_bootstrap() -> None:
    html = '<script>requireLazy(["LSD"],function(){});</script>["LSD",[],{"token":"AdQGFw_OMy8GbnrB01N5oQtOM5g"}]'
    assert _extract_lsd_token(html) == "AdQGFw_OMy8GbnrB01N5oQtOM5g"


def test_meta_target_office_queries_keep_only_target_countries() -> None:
    payload = {
        "data": {
            "job_search_filters": {
                "locations": [
                    {"location_display_name": "Berlin, Germany", "country": "Germany", "is_remote": False},
                    {"location_display_name": "Zurich, Switzerland", "country": "Switzerland", "is_remote": False},
                    {"location_display_name": "Remote, Germany", "country": "Germany", "is_remote": True},
                    {"location_display_name": "London, UK", "country": "UK", "is_remote": False},
                    {"location_display_name": "Europe & Middle East", "country": "", "is_remote": False},
                ]
            }
        }
    }
    assert _target_office_queries(payload, ["Germany", "Switzerland", "Netherlands", "Romania"]) == [
        "Berlin",
        "Zurich",
    ]


def test_meta_extract_job_posting_reads_json_ld() -> None:
    html = """
    <script type="application/ld+json">
    {"@context":"http://schema.org/","@type":"JobPosting","title":"AI Research Scientist","description":"Build multimodal models.","responsibilities":"Ship research systems.","qualifications":"PhD or equivalent.","employmentType":"Full time","datePosted":"2026-03-11T09:06:34-08:00","jobLocation":[{"@type":"Place","name":"Zurich, Switzerland","address":{"@type":"PostalAddress","addressCountry":{"@type":"Country","name":["CHE"]}}}]}
    </script>
    """
    posting = meta_extract_job_posting(html)
    assert posting["title"] == "AI Research Scientist"
    assert posting["employmentType"] == "Full time"
    assert posting["jobLocation"][0]["name"] == "Zurich, Switzerland"


def test_spotify_target_locations_keep_only_target_countries() -> None:
    item = {
        "locations": [
            {"location": "Berlin", "slug": "berlin"},
            {"location": "Düsseldorf", "slug": "dusseldorf"},
            {"location": "New York", "slug": "new-york"},
        ]
    }
    assert spotify_target_locations(item) == ["Berlin", "Düsseldorf"]


def test_spotify_extract_job_payload_reads_next_data() -> None:
    html = """
    <script id="__NEXT_DATA__" type="application/json">
    {"props":{"pageProps":{"job":{"id":"uuid-1","text":"Podcast Partner Manager, Berlin","createdAt":1772643115160,"state":"published","urls":{"show":"https://jobs.lever.co/spotify/uuid-1"},"categories":{"commitment":"Permanent","location":"Berlin","locations":["Berlin"]},"content":{"description":"Base description","descriptionHtml":"<p>Base description</p>","closingHtml":"<p>Closing text</p>","lists":[{"text":"What You'll Do","content":"<li>Do things</li>"}]}}}}}
    </script>
    """
    job = spotify_extract_job_payload(html)
    assert job["id"] == "uuid-1"
    assert job["text"] == "Podcast Partner Manager, Berlin"
    assert job["categories"]["location"] == "Berlin"
    assert job["content"]["lists"][0]["text"] == "What You'll Do"
