from __future__ import annotations

from job_search.adapters.google import (
    _detail_url,
    _extract_list_section,
    _extract_section,
    _extract_title,
)


def test_google_detail_url_preserves_location_query() -> None:
    url = _detail_url("123-role-name", "Switzerland")
    assert "123-role-name" in url
    assert "location=Switzerland" in url


def test_google_extracts_title_and_sections() -> None:
    html = """
    <html>
      <head>
        <title>Software Engineer III, Infrastructure, YouTube — Google Careers</title>
      </head>
      <body>
        <div class="KwJkGe">
          <h3>Minimum qualifications:</h3>
          <ul>
            <li>Bachelor's degree or equivalent practical experience.</li>
            <li>2 years of experience with distributed systems.</li>
          </ul>
          <br>
          <h3>Preferred qualifications:</h3>
          <ul>
            <li>Experience with large-scale systems.</li>
          </ul>
        </div>
        <div class="aG5W3">
          <h3>About the job</h3>
          Google's software engineers develop large-scale systems.
        </div>
        <div class="BDNOWe">
          <h3>Responsibilities</h3>
          <ul>
            <li>Design backend features.</li>
            <li>Collaborate with product and infra teams.</li>
          </ul>
        </div>
        <div class="bE3reb"></div>
      </body>
    </html>
    """

    assert _extract_title(html, "123-software-engineer") == "Software Engineer III, Infrastructure, YouTube"
    assert "Bachelor's degree" in _extract_list_section(html, "Minimum qualifications:")
    assert "Experience with large-scale systems." in _extract_list_section(html, "Preferred qualifications:")
    assert "Google's software engineers develop large-scale systems." in _extract_section(html, "About the job")
    assert "Design backend features." in _extract_list_section(html, "Responsibilities")
