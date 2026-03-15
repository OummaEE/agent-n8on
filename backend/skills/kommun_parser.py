"""
Skill: kommun_parser
Description: Parse Swedish municipality (kommun) websites and collect contact data.
Author: Jane's Agent Builder
"""

SKILL_NAME = "kommun_parser"
SKILL_VERSION = "1.0"
SKILL_DESCRIPTION = "Parse Swedish municipality websites, collect contacts, emails, phone numbers"
SKILL_TOOLS = {
    "parse_kommun": {
        "description": "Parse a Swedish kommun website and extract contacts, departments, emails, phones",
        "args": {"url": "URL of the kommun website (e.g. https://www.stockholm.se)"},
        "example": '{"tool": "parse_kommun", "args": {"url": "https://www.stockholm.se"}}'
    },
    "search_kommuns": {
        "description": "Search for Swedish municipalities by name or region and return their websites",
        "args": {"query": "Search query (e.g. 'Stockholm' or 'Skåne')"},
        "example": '{"tool": "search_kommuns", "args": {"query": "Skåne"}}'
    }
}

# Swedish kommun base URLs (top 50)
KOMMUN_URLS = {
    "stockholm": "https://www.stockholm.se",
    "göteborg": "https://goteborg.se",
    "malmö": "https://malmo.se",
    "uppsala": "https://www.uppsala.se",
    "linköping": "https://www.linkoping.se",
    "örebro": "https://www.orebro.se",
    "västerås": "https://www.vasteras.se",
    "norrköping": "https://www.norrkoping.se",
    "helsingborg": "https://helsingborg.se",
    "jönköping": "https://www.jonkoping.se",
    "umeå": "https://www.umea.se",
    "lund": "https://www.lund.se",
    "borås": "https://www.boras.se",
    "sundsvall": "https://www.sundsvall.se",
    "gävle": "https://www.gavle.se",
    "eskilstuna": "https://www.eskilstuna.se",
    "halmstad": "https://www.halmstad.se",
    "södertälje": "https://www.sodertalje.se",
    "karlstad": "https://www.karlstad.se",
    "växjö": "https://www.vaxjo.se",
    "täby": "https://www.taby.se",
    "solna": "https://www.solna.se",
    "nacka": "https://www.nacka.se",
    "huddinge": "https://www.huddinge.se",
    "haninge": "https://www.haninge.se",
}

REGIONS = {
    "skåne": ["malmö", "helsingborg", "lund"],
    "västra götaland": ["göteborg", "borås"],
    "stockholm": ["stockholm", "solna", "nacka", "huddinge", "täby", "haninge", "södertälje"],
    "östergötland": ["linköping", "norrköping"],
    "västmanland": ["västerås"],
    "örebro": ["örebro"],
    "jönköping": ["jönköping"],
    "västerbotten": ["umeå"],
    "gävleborg": ["gävle"],
    "södermanland": ["eskilstuna"],
    "halland": ["halmstad"],
    "värmland": ["karlstad"],
    "kronoberg": ["växjö"],
    "västernorrland": ["sundsvall"],
    "uppsala": ["uppsala"],
}


def parse_kommun(url: str) -> str:
    """Parse a kommun website and extract contact information"""
    import requests
    import re

    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept-Language": "sv-SE,sv;q=0.9,en;q=0.5"
        }
        resp = requests.get(url, headers=headers, timeout=15, allow_redirects=True)
        resp.encoding = resp.apparent_encoding or 'utf-8'
        html = resp.text

        # Extract emails
        emails = list(set(re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', html)))
        # Filter out image/css/js emails
        emails = [e for e in emails if not e.endswith(('.png', '.jpg', '.gif', '.css', '.js'))]

        # Extract phone numbers (Swedish format)
        phones = list(set(re.findall(r'(?:tel:|telefon|phone|ring)[\s:]*([+\d\s\-()]{7,20})', html, re.IGNORECASE)))
        # Also try generic Swedish phone patterns
        phones += list(set(re.findall(r'0\d{1,3}[\s-]?\d{2,3}[\s-]?\d{2,4}[\s-]?\d{0,4}', html)))
        phones = list(set(phones))[:20]

        # Extract title
        import html as html_module
        title_match = re.search(r'<title[^>]*>(.*?)</title>', html, re.IGNORECASE | re.DOTALL)
        title = html_module.unescape(title_match.group(1).strip()) if title_match else url

        # Extract contact page links
        contact_links = re.findall(r'href=["\']([^"\']*(?:kontakt|contact|kundtjanst|kundservice)[^"\']*)["\']', html, re.IGNORECASE)
        contact_links = list(set(contact_links))[:10]

        # Extract address patterns (Swedish)
        addresses = re.findall(r'\d{3}\s?\d{2}\s+[A-ZÅÄÖ][a-zåäö]+', html)
        addresses = list(set(addresses))[:5]

        result_parts = [f"=== {title} ===", f"URL: {url}", ""]

        if emails:
            result_parts.append(f"📧 Emails ({len(emails)}):")
            for e in emails[:15]:
                result_parts.append(f"  {e}")
            result_parts.append("")

        if phones:
            result_parts.append(f"📞 Phones ({len(phones)}):")
            for p in phones[:10]:
                result_parts.append(f"  {p.strip()}")
            result_parts.append("")

        if addresses:
            result_parts.append(f"📍 Addresses:")
            for a in addresses:
                result_parts.append(f"  {a}")
            result_parts.append("")

        if contact_links:
            result_parts.append(f"🔗 Contact pages:")
            for link in contact_links[:5]:
                if link.startswith('/'):
                    from urllib.parse import urljoin
                    link = urljoin(url, link)
                result_parts.append(f"  {link}")

        if not emails and not phones:
            result_parts.append("No direct contacts found on main page.")
            result_parts.append("Try parsing the /kontakt or /contact subpage.")

        return "\n".join(result_parts)

    except Exception as e:
        return f"Error parsing {url}: {str(e)}"


def search_kommuns(query: str) -> str:
    """Search for Swedish municipalities"""
    query_lower = query.lower().strip()
    results = []

    # Search by region
    for region, kommuns in REGIONS.items():
        if query_lower in region:
            results.append(f"=== Region: {region.title()} ===")
            for k in kommuns:
                url = KOMMUN_URLS.get(k, f"https://www.{k}.se")
                results.append(f"  {k.title()}: {url}")

    # Search by kommun name
    for kommun, url in KOMMUN_URLS.items():
        if query_lower in kommun:
            results.append(f"{kommun.title()}: {url}")

    if not results:
        # Suggest URL pattern
        slug = query_lower.replace(' ', '').replace('ö', 'o').replace('ä', 'a').replace('å', 'a')
        results.append(f"Kommun '{query}' not in database.")
        results.append(f"Try: https://www.{slug}.se or https://{slug}.se")
        results.append(f"Or search: https://www.google.com/search?q={query}+kommun+kontakt")

    return "\n".join(results)


# Tool router for this skill
TOOLS = {
    "parse_kommun": lambda args: parse_kommun(args.get("url", "")),
    "search_kommuns": lambda args: search_kommuns(args.get("query", "")),
}
