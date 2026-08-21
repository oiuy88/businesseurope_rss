import html
import xml.etree.ElementTree as ET

from datetime import datetime, timezone
from email.utils import format_datetime
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup


# ============================================================
# CONFIGURATION
# ============================================================

BASE_URL = "https://www.businesseurope.eu"

PUBLICATIONS_URL = (
    "https://www.businesseurope.eu/publications/"
)

OUTPUT_FILE = "businesseurope.xml"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 "
        "(compatible; BusinessEurope-RSS/1.0)"
    ),
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "en-GB,en;q=0.9",
}


# ============================================================
# FETCH PAGE
# ============================================================

def fetch_page(url):

    print()
    print("Fetching:")
    print(url)

    response = requests.get(
        url,
        headers=HEADERS,
        timeout=60,
    )

    print(
        f"HTTP status: {response.status_code}"
    )

    response.raise_for_status()

    return response.text


# ============================================================
# PARSE DATE
# ============================================================

def parse_date(date_text):

    if not date_text:
        return None

    date_text = date_text.strip()

    formats = [
        "%d.%m.%Y",
        "%d/%m/%Y",
        "%d-%m-%Y",
    ]

    for date_format in formats:

        try:

            return datetime.strptime(
                date_text,
                date_format
            ).replace(
                tzinfo=timezone.utc
            )

        except ValueError:
            pass

    return None


# ============================================================
# EXTRACT PUBLICATIONS
# ============================================================

def extract_publications(html_content):

    soup = BeautifulSoup(
        html_content,
        "html.parser"
    )

    publications = []

    # --------------------------------------------------------
    # Find links containing publication pages.
    #
    # BusinessEurope publication URLs are under:
    # /publications/
    # --------------------------------------------------------

    for link in soup.find_all("a"):

        href = link.get(
            "href"
        )

        if not href:
            continue

        url = urljoin(
            BASE_URL,
            href
        )

        # Only BusinessEurope publication pages.
        if not url.startswith(
            BASE_URL + "/publications/"
        ):
            continue

        # Don't treat the main archive itself as an item.
        if url.rstrip("/") == (
            PUBLICATIONS_URL.rstrip("/")
        ):
            continue

        title = link.get_text(
            " ",
            strip=True
        )

        if not title:
            continue

        # Ignore generic navigation links.
        ignored_titles = {
            "read more",
            "publications",
            "next",
            "previous",
            "reset filters",
        }

        if title.lower() in ignored_titles:
            continue

        publications.append(
            {
                "title": title,
                "url": url,
            }
        )

    # --------------------------------------------------------
    # Deduplicate URLs
    # --------------------------------------------------------

    unique = {}

    for publication in publications:

        unique[
            publication["url"]
        ] = publication

    return list(
        unique.values()
    )


# ============================================================
# GET PUBLICATION DETAILS
# ============================================================

def get_publication_details(
    publication
):

    html_content = fetch_page(
        publication["url"]
    )

    soup = BeautifulSoup(
        html_content,
        "html.parser"
    )

    # --------------------------------------------------------
    # Title
    # --------------------------------------------------------

    title = publication["title"]

    heading = soup.find(
        "h1"
    )

    if heading:

        heading_text = heading.get_text(
            " ",
            strip=True
        )

        if heading_text:
            title = heading_text

    # --------------------------------------------------------
    # Find publication date
    # --------------------------------------------------------

    date = None

    # Search visible text for common BusinessEurope
    # date format: DD.MM.YYYY
    text = soup.get_text(
        " ",
        strip=True
    )

    import re

    date_match = re.search(
        r"\b(\d{2}\.\d{2}\.\d{4})\b",
        text
    )

    if date_match:

        date = parse_date(
            date_match.group(1)
        )

    return {
        "title": title,
        "url": publication["url"],
        "date": date,
    }


# ============================================================
# CREATE RSS
# ============================================================

def create_rss(
    publications
):

    rss = ET.Element(
        "rss",
        {
            "version": "2.0"
        }
    )

    channel = ET.SubElement(
        rss,
        "channel"
    )

    ET.SubElement(
        channel,
        "title"
    ).text = (
        "BusinessEurope Publications"
    )

    ET.SubElement(
        channel,
        "link"
    ).text = PUBLICATIONS_URL

    ET.SubElement(
        channel,
        "description"
    ).text = (
        "Latest publications from BusinessEurope"
    )

    ET.SubElement(
        channel,
        "language"
    ).text = "en"

    ET.SubElement(
        channel,
        "lastBuildDate"
    ).text = format_datetime(
        datetime.now(
            timezone.utc
        )
    )

    # --------------------------------------------------------
    # Sort newest first.
    #
    # Items without dates go to the end.
    # --------------------------------------------------------

    publications.sort(
        key=lambda item: (
            item["date"] is not None,
            item["date"] or datetime.min.replace(
                tzinfo=timezone.utc
            ),
        ),
        reverse=True,
    )

    for publication in publications:

        item = ET.SubElement(
            channel,
            "item"
        )

        title = publication[
            "title"
        ]

        url = publication[
            "url"
        ]

        ET.SubElement(
            item,
            "title"
        ).text = title

        ET.SubElement(
            item,
            "link"
        ).text = url

        ET.SubElement(
            item,
            "guid",
            {
                "isPermaLink": "true"
            }
        ).text = url

        if publication["date"]:

            ET.SubElement(
                item,
                "pubDate"
            ).text = format_datetime(
                publication["date"]
            )

        ET.SubElement(
            item,
            "description"
        ).text = html.escape(
            "BusinessEurope publication: "
            + title
        )

    return ET.ElementTree(
        rss
    )


# ============================================================
# MAIN
# ============================================================

def main():

    print("=" * 60)
    print("BUSINESSEUROPE RSS GENERATOR")
    print("=" * 60)

    all_publications = []

    # --------------------------------------------------------
    # FIRST 5 PAGES
    #
    # We deliberately start conservatively.
    # --------------------------------------------------------

    for page in range(1, 6):

        if page == 1:

            url = PUBLICATIONS_URL

        else:

            url = (
                PUBLICATIONS_URL
                + f"?sf_paged={page}"
            )

        print()
        print(
            f"Fetching publications page {page}..."
        )

        page_html = fetch_page(
            url
        )

        publications = extract_publications(
            page_html
        )

        print(
            f"Found "
            f"{len(publications)} "
            f"publication links"
        )

        all_publications.extend(
            publications
        )

    # --------------------------------------------------------
    # Deduplicate
    # --------------------------------------------------------

    unique = {}

    for publication in all_publications:

        unique[
            publication["url"]
        ] = publication

    publications = list(
        unique.values()
    )

    print()
    print(
        f"Unique publications found: "
        f"{len(publications)}"
    )

    # --------------------------------------------------------
    # Get publication details
    #
    # Limit to the first 100 for now.
    # --------------------------------------------------------

    publications = publications[:100]

    detailed = []

    for number, publication in enumerate(
        publications,
        start=1
    ):

        print()
        print(
            f"[{number}/{len(publications)}] "
            f"{publication['title']}"
        )

        try:

            details = get_publication_details(
                publication
            )

            detailed.append(
                details
            )

        except Exception as error:

            print(
                f"WARNING: Could not retrieve "
                f"publication: {error}"
            )

            # Keep the basic listing information.
            detailed.append(
                publication
            )

    # --------------------------------------------------------
    # Remove duplicate URLs again
    # --------------------------------------------------------

    unique = {}

    for publication in detailed:

        unique[
            publication["url"]
        ] = publication

    detailed = list(
        unique.values()
    )

    print()
    print(
        f"Final RSS items: "
        f"{len(detailed)}"
    )

    if not detailed:

        raise RuntimeError(
            "No BusinessEurope publications "
            "were found."
        )

    # --------------------------------------------------------
    # Generate RSS
    # --------------------------------------------------------

    rss = create_rss(
        detailed
    )

    ET.indent(
        rss,
        space="  "
    )

    rss.write(
        OUTPUT_FILE,
        encoding="utf-8",
        xml_declaration=True
    )

    print()
    print(
        f"RSS successfully written to "
        f"{OUTPUT_FILE}"
    )

    print()
    print("=" * 60)
    print("SUCCESS")
    print("=" * 60)


if __name__ == "__main__":
    main()
