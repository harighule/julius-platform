import re as _re
import os as _os
import json as _json
import urllib.request as _urllib_req

_UK_PHONE_RE = _re.compile(
    r'(?:(?:\+44\s?)|(?:0))(?:7\d{3}\s?\d{3}\s?\d{3,4}|\d{4}\s?\d{3}\s?\d{3,4})'
)
_EMAIL_RE = _re.compile(r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}')
_BAD_EMAIL = _re.compile(r'(noreply|no-reply|github|example|placeholder|test@|sentry)', _re.I)


def _scrape_url_for_contact(url: str) -> tuple:
    email = ""
    phone = ""
    try:
        if not url.startswith("http"):
            url = "https://" + url
        req = _urllib_req.Request(url, headers={"User-Agent": "Mozilla/5.0"}, method="GET")
        with _urllib_req.urlopen(req, timeout=6) as resp:
            text = resp.read(65536).decode("utf-8", errors="ignore")
        tel = _re.search(r'tel:([\+\d\s\-\(\)]{7,16})', text)
        if tel:
            phone = tel.group(1).strip()
        if not phone:
            m = _UK_PHONE_RE.search(text)
            if m:
                phone = m.group().strip()
        m = _EMAIL_RE.search(text)
        if m and not _BAD_EMAIL.search(m.group()):
            email = m.group()
    except Exception:
        pass
    return email, phone


def _gpt_find_contact(name: str, handle: str, github_url: str, company: str, blog: str) -> tuple:
    api_key = _os.getenv("OPENAI_API_KEY", "")
    if not api_key:
        return "", ""
    prompt = (
        f"Find the professional email and UK phone number for this person.\n"
        f"Name: {name}\nGitHub: {github_url}\nHandle: {handle}\n"
        f"Company: {company}\nWebsite: {blog}\n\n"
        f"Search their GitHub, personal site, LinkedIn, company page.\n"
        f"Return ONLY JSON: {{\"email\": \"...\", \"phone\": \"...\"}}\n"
        f"Phone must be UK format. Use empty string if not found. Do not invent."
    )
    try:
        payload = _json.dumps({
            "model": "gpt-4o-mini",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0,
            "max_tokens": 100,
        }).encode()
        req = _urllib_req.Request(
            "https://api.openai.com/v1/chat/completions",
            data=payload,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with _urllib_req.urlopen(req, timeout=15) as resp:
            data = _json.loads(resp.read())
        text = data["choices"][0]["message"]["content"].strip()
        text = text.replace("```json", "").replace("```", "").strip()
        result = _json.loads(text)
        email = str(result.get("email") or "").strip()
        phone = str(result.get("phone") or "").strip()
        if "@" not in email or _BAD_EMAIL.search(email):
            email = ""
        if phone and not any(c.isdigit() for c in phone):
            phone = ""
        return email, phone
    except Exception:
        return "", ""


def extract_contact_from_profile(profile: dict) -> tuple:
    email = ""
    phone = ""
    email_source = ""
    phone_source = ""
    blog = ""

    # 1. Already stored contact block
    contact = profile.get("contact") or {}
    if contact.get("email"):
        email = contact["email"]
        email_source = contact.get("email_source") or "stored"
    if contact.get("phone"):
        phone = contact["phone"]
        phone_source = contact.get("phone_source") or "stored"

    if email and phone:
        return email, phone, email_source, phone_source

    # 2. GitHub raw signals
    raw = profile.get("raw_signals") or {}
    github_user = raw.get("github_user") or {}

    if not email:
        gh_email = str(github_user.get("email") or "").strip()
        if gh_email and "@" in gh_email and not _BAD_EMAIL.search(gh_email):
            email = gh_email
            email_source = "github_profile"

    bio = str(github_user.get("bio") or "")
    if not email:
        m = _EMAIL_RE.search(bio)
        if m and not _BAD_EMAIL.search(m.group()):
            email = m.group()
            email_source = "github_bio"
    if not phone:
        m = _UK_PHONE_RE.search(bio)
        if m:
            phone = m.group().strip()
            phone_source = "github_bio"

    # 3. Blog / personal website
    blog = str(github_user.get("blog") or "").strip()
    if blog and (not email or not phone):
        se, sp = _scrape_url_for_contact(blog)
        if se and not email:
            email = se
            email_source = "personal_site"
        if sp and not phone:
            phone = sp
            phone_source = "personal_site"

    # 4. Profile URL scrape
    identity = profile.get("identity_anchors") or {}
    profile_url = str(identity.get("profile_url") or "").strip()
    if profile_url and not email:
        se, _ = _scrape_url_for_contact(profile_url)
        if se:
            email = se
            email_source = "profile_url_scrape"

    # 5. GPT-4o fallback
    if not email:
        name = str(identity.get("display_name") or identity.get("handle") or "")
        handle = str(identity.get("handle") or "")
        github_url = str(identity.get("profile_url") or "")
        situational = profile.get("situational_intelligence") or {}
        company = str(situational.get("org") or "")
        gpt_email, gpt_phone = _gpt_find_contact(name, handle, github_url, company, blog)
        if gpt_email:
            email = gpt_email
            email_source = "gpt4o_search"
        if gpt_phone and not phone:
            phone = gpt_phone
            phone_source = "gpt4o_search"

    return email, phone, email_source, phone_source