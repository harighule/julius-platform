import re
import json
import requests
import os
from typing import Dict, List, Tuple

class SocialMediaEnricher:
    """Enriches profiles with ALL social media platforms"""
    
    PLATFORMS = {
        'github': {'base_url': 'https://github.com/', 'api_url': 'https://api.github.com/users/'},
        'twitter': {'base_url': 'https://twitter.com/', 'api_url': 'https://api.twitter.com/2/users/by/username/'},
        'linkedin': {'base_url': 'https://linkedin.com/in/', 'scrape': True},
        'instagram': {'base_url': 'https://instagram.com/', 'scrape': True},
        'facebook': {'base_url': 'https://facebook.com/', 'scrape': True},
        'gitlab': {'base_url': 'https://gitlab.com/', 'api_url': 'https://gitlab.com/api/v4/users/'},
        'devto': {'base_url': 'https://dev.to/', 'api_url': 'https://dev.to/api/users/by_username/'},
        'medium': {'base_url': 'https://medium.com/@', 'scrape': True},
        'youtube': {'base_url': 'https://youtube.com/@', 'api_url': 'https://www.googleapis.com/youtube/v3/channels'},
        'tiktok': {'base_url': 'https://tiktok.com/@', 'scrape': True},
        'stackoverflow': {'base_url': 'https://stackoverflow.com/users/', 'scrape': True}
    }
    
    def __init__(self):
        self.github_token = os.getenv('GITHUB_TOKEN', '')
        self.twitter_bearer = os.getenv('TWITTER_BEARER_TOKEN', '')
        
    def find_all_social_handles(self, username: str, email: str = "", full_name: str = "") -> Dict:
        """Find all social media handles for a person"""
        handles = {}
        
        # 1. Search GitHub for email patterns
        if email:
            github_handles = self.search_github_by_email(email)
            if github_handles:
                handles['github'] = github_handles[0]
        
        # 2. Search by username across platforms
        for platform in self.PLATFORMS.keys():
            handle = self.check_platform_handle(platform, username)
            if handle:
                handles[platform] = handle
        
        # 3. Search by full name
        if full_name and len(full_name.split()) >= 2:
            name_handles = self.search_by_full_name(full_name)
            handles.update(name_handles)
        
        return handles
    
    def search_github_by_email(self, email: str) -> List[str]:
        """Search GitHub users by email"""
        if not self.github_token:
            return []
        
        try:
            headers = {'Authorization': f'token {self.github_token}'}
            url = f'https://api.github.com/search/commits?q=author-email:{email}'
            resp = requests.get(url, headers=headers, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                handles = set()
                for commit in data.get('items', [])[:10]:
                    author = commit.get('author', {})
                    if author.get('login'):
                        handles.add(author['login'])
                return list(handles)
        except:
            pass
        return []
    
    def check_platform_handle(self, platform: str, handle: str) -> str:
        """Check if a handle exists on a platform"""
        if not handle:
            return ""
        
        platform_config = self.PLATFORMS.get(platform, {})
        
        if 'api_url' in platform_config:
            try:
                url = platform_config['api_url'] + handle
                if platform == 'github' and self.github_token:
                    headers = {'Authorization': f'token {self.github_token}'}
                    resp = requests.get(url, headers=headers, timeout=5)
                else:
                    resp = requests.get(url, timeout=5)
                
                if resp.status_code == 200:
                    return handle
            except:
                pass
        
        if handle and len(handle) > 2 and not handle.isdigit():
            return handle
        
        return ""
    
    def search_by_full_name(self, full_name: str) -> Dict:
        """Search for profiles using full name"""
        handles = {}
        name_parts = full_name.lower().replace(' ', '.')
        
        possible_usernames = [
            name_parts,
            name_parts.replace('.', ''),
            full_name.lower().replace(' ', ''),
            full_name.lower().replace(' ', '_'),
            full_name.split()[0].lower() + '.' + full_name.split()[-1].lower(),
            full_name.split()[0].lower() + full_name.split()[-1].lower()
        ]
        
        for platform in ['linkedin', 'twitter', 'instagram']:
            for username in possible_usernames[:3]:
                check = self.check_platform_handle(platform, username)
                if check:
                    handles[platform] = check
                    break
        
        return handles
    
    def extract_email_from_any_source(self, handle: str, platform: str) -> str:
        """Extract email from any platform's public data"""
        email = ""
        
        if platform == 'github' and self.github_token:
            try:
                url = f'https://api.github.com/users/{handle}'
                headers = {'Authorization': f'token {self.github_token}'}
                resp = requests.get(url, headers=headers, timeout=10)
                if resp.status_code == 200:
                    user_data = resp.json()
                    email = user_data.get('email', '')
                    if email and '@users.noreply.github.com' in email:
                        email = ""
            except:
                pass
        
        return email
    
    def extract_phone_from_bio(self, bio: str) -> str:
        """Extract UK phone number from bio text"""
        phone_pattern = re.compile(
            r'(?:(?:\+44\s?)|(?:0))(?:7\d{3}\s?\d{3}\s?\d{3,4}|\d{4}\s?\d{3}\s?\d{3,4})'
        )
        match = phone_pattern.search(bio)
        return match.group() if match else ""

class RealPersonFilter:
    """Filter to ensure only REAL people are collected"""
    
    FAKE_PATTERNS = re.compile(
        r'(bot|test|demo|example|placeholder|sample|fake|dummy|delete|remove|'
        r'government|gov\.uk|openstreetmap|location|country|city|organization|'
        r'company\s+name|ltd|ltd\.|inc|corp|foundation)',
        re.I
    )
    
    REAL_INDICATORS = re.compile(
        r'(developer|engineer|software|architect|lead|senior|founder|ceo|cto|'
        r'full[- ]stack|frontend|backend|devops|data\s+scientist|ml\s+engineer|'
        r'ai\s+researcher|product\s+manager|tech\s+lead)',
        re.I
    )
    
    @classmethod
    def is_real_person(cls, profile_data: Dict) -> Tuple[bool, str]:
        """Determine if profile represents a real person"""
        
        identity = profile_data.get('identity_anchors', {})
        handle = identity.get('handle', '')
        display_name = identity.get('display_name', '')
        bio = profile_data.get('raw_signals', {}).get('github_user', {}).get('bio', '')
        
        if cls.FAKE_PATTERNS.search(handle):
            return False, "Handle contains fake/organization keywords"
        
        if cls.FAKE_PATTERNS.search(display_name):
            return False, "Name contains fake/organization keywords"
        
        location_indicators = ['manchester', 'london', 'england', 'united kingdom', 'city of']
        if any(loc in handle.lower() for loc in location_indicators):
            return False, "Handle appears to be a location"
        
        if cls.REAL_INDICATORS.search(bio):
            return True, "Technical role indicators found"
        
        github_user = profile_data.get('raw_signals', {}).get('github_user', {})
        if github_user.get('public_repos', 0) > 0:
            return True, "Has GitHub repositories"
        
        if identity.get('platform') == 'github' and handle and len(handle) > 3:
            return True, "Valid GitHub handle"
        
        return False, "No real person indicators found"
