import re
import os
import json
import urllib.request
from typing import Tuple

EMAIL_RE = re.compile(r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}')
PHONE_RE = re.compile(r'(?:(?:\+44\s?)|(?:0))(?:7\d{3}\s?\d{3}\s?\d{3,4}|\d{4}\s?\d{3}\s?\d{3,4})')
BAD_EMAILS = re.compile(r'(noreply|no-reply|example|placeholder|test@|@users\.noreply\.github)', re.I)

def scrape_url_for_contact(url: str) -> Tuple[str, str]:
    """Scrape a URL for email and phone"""
    email = ""
    phone = ""
    try:
        if not url.startswith("http"):
            url = "https://" + url
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}, method="GET")
        with urllib.request.urlopen(req, timeout=8) as resp:
            text = resp.read(65536).decode("utf-8", errors="ignore")
        
        email_match = EMAIL_RE.search(text)
        if email_match and not BAD_EMAILS.search(email_match.group()):
            email = email_match.group()
        
        phone_match = PHONE_RE.search(text)
        if phone_match:
            phone = phone_match.group()
    except Exception:
        pass
    return email, phone

def gpt_search_contact(name: str, handle: str, github_url: str, company: str, platform: str) -> Tuple[str, str]:
    """Use GPT-4o to search for contact info"""
    api_key = os.getenv("OPENAI_API_KEY", "")
    if not api_key:
        return "", ""
    
    prompt = f"""Find the professional email and UK phone number for this person.

Name: {name}
Handle: {handle}
Platform: {platform}
GitHub URL: {github_url}
Company: {company}

Search their:
- GitHub profile (if public email exists)
- Personal website
- LinkedIn (if findable)
- Twitter bio
- StackOverflow profile

Return ONLY JSON: {{"email": "email@example.com", "phone": "07700 900123"}}
Use empty string if not found. DO NOT invent data.
Phone must be UK format (starts with 07 or +44)."""
    
    try:
        payload = json.dumps({
            "model": "gpt-4o-mini",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0,
            "max_tokens": 150
        }).encode()
        
        req = urllib.request.Request(
            "https://api.openai.com/v1/chat/completions",
            data=payload,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            },
            method="POST"
        )
        
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read())
        
        result_text = data["choices"][0]["message"]["content"].strip()
        result_text = result_text.replace("```json", "").replace("```", "").strip()
        result = json.loads(result_text)
        
        email = result.get("email", "").strip()
        phone = result.get("phone", "").strip()
        
        if email and ("@" not in email or BAD_EMAILS.search(email)):
            email = ""
        if phone and not any(c.isdigit() for c in phone):
            phone = ""
        
        return email, phone
    except Exception as e:
        print(f"GPT search error: {e}")
        return "", ""

def extract_contact_aggressive(profile: dict) -> Tuple[str, str, dict]:
    """Aggressively extract email and phone - tries everything including GPT-4o."""
    email = ""
    phone = ""
    sources = {"email": "", "phone": ""}
    
    # 1. Check existing contact block
    contact = profile.get("contact") or {}
    if contact.get("email"):
        email = contact["email"]
        sources["email"] = contact.get("email_source", "stored")
    if contact.get("phone"):
        phone = contact["phone"]
        sources["phone"] = contact.get("phone_source", "stored")
    
    if email and phone:
        return email, phone, sources
    
    # 2. Extract from identity anchors
    identity = profile.get("identity_anchors") or {}
    handle = identity.get("handle", "")
    display_name = identity.get("display_name", handle)
    platform = identity.get("platform", "")
    profile_url = identity.get("profile_url", "")
    
    # 3. Check raw_signals for any data
    raw = profile.get("raw_signals") or {}
    
    # 3a. GitHub user data
    github_user = raw.get("github_user")
    if github_user and isinstance(github_user, dict):
        if not email:
            gh_email = github_user.get("email", "")
            if gh_email and "@" in gh_email and not BAD_EMAILS.search(gh_email):
                email = gh_email
                sources["email"] = "github_api"
        
        if not phone:
            bio = github_user.get("bio", "")
            phone_match = PHONE_RE.search(bio)
            if phone_match:
                phone = phone_match.group()
                sources["phone"] = "github_bio"
        
        blog = github_user.get("blog", "")
        if blog and not email:
            se, sp = scrape_url_for_contact(blog)
            if se:
                email = se
                sources["email"] = "personal_site"
            if sp and not phone:
                phone = sp
                sources["phone"] = "personal_site"
    
    # 4. Scrape the profile URL directly
    if profile_url and not email:
        scraped_email, scraped_phone = scrape_url_for_contact(profile_url)
        if scraped_email:
            email = scraped_email
            sources["email"] = "profile_url_scrape"
        if scraped_phone and not phone:
            phone = scraped_phone
            sources["phone"] = "profile_url_scrape"
    
    # 5. GPT-4o fallback
    if not email and (platform == "github" or handle):
        situational = profile.get("situational_intelligence") or {}
        company = situational.get("org", "")
        
        gpt_email, gpt_phone = gpt_search_contact(
            name=display_name,
            handle=handle,
            github_url=profile_url if platform == "github" else "",
            company=company,
            platform=platform
        )
        
        if gpt_email:
            email = gpt_email
            sources["email"] = "gpt4o_search"
        if gpt_phone and not phone:
            phone = gpt_phone
            sources["phone"] = "gpt4o_search"
    
    return email, phone, sources
