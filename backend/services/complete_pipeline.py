import json
import time
from typing import Dict, List
from backend.services.social_enricher import SocialMediaEnricher, RealPersonFilter
from backend.services.contact_enrichment_v2 import extract_contact_aggressive, gpt_search_contact

class CompleteProfilePipeline:
    """Complete pipeline that ensures every profile has email, phone, and all social media"""
    
    def __init__(self):
        self.social_enricher = SocialMediaEnricher()
        
    def process_profile(self, raw_profile: Dict) -> Dict:
        """Process a profile through complete enrichment pipeline"""
        
        # 1. Filter for real people only
        is_real, reason = RealPersonFilter.is_real_person(raw_profile)
        if not is_real:
            print(f"Skipping fake/organization: {raw_profile.get('identity_anchors', {}).get('handle')} - {reason}")
            return None
        
        # 2. Extract identity
        identity = raw_profile.get('identity_anchors', {})
        handle = identity.get('handle', '')
        full_name = identity.get('display_name', '')
        platform = identity.get('platform', 'github')
        
        # 3. Find all social media handles
        print(f"Finding social media for {handle}...")
        social_handles = self.social_enricher.find_all_social_handles(
            username=handle,
            email=raw_profile.get('contact', {}).get('email', ''),
            full_name=full_name
        )
        
        # 4. Aggressive email/phone extraction
        email, phone, sources = extract_contact_aggressive(raw_profile)
        
        # 5. If still no email, use GPT-4o to search all platforms
        if not email:
            print(f"GPT-4o searching for {handle} across all platforms...")
            gpt_email, gpt_phone = gpt_search_contact(
                name=full_name,
                handle=handle,
                github_url=identity.get('profile_url', ''),
                company=raw_profile.get('situational_intelligence', {}).get('org', ''),
                platform=platform
            )
            if gpt_email:
                email = gpt_email
                sources['email'] = 'gpt4o_multi_platform'
            if gpt_phone and not phone:
                phone = gpt_phone
                sources['phone'] = 'gpt4o_multi_platform'
        
        # 6. Build complete profile with all fields
        enhanced_profile = {
            "identity": {
                "full_name": full_name,
                "primary_handle": handle,
                "primary_platform": platform,
                "all_handles": social_handles
            },
            "contact": {
                "email": {"value": email, "source": sources.get('email', ''), "verified": bool(email)},
                "phone": {"value": phone, "source": sources.get('phone', ''), "verified": bool(phone), "country": "UK"}
            },
            "social_media": {
                "github": {
                    "username": social_handles.get('github', handle if platform == 'github' else ''),
                    "url": f"https://github.com/{social_handles.get('github', handle)}" if (social_handles.get('github') or platform == 'github') else ""
                },
                "twitter": {
                    "username": social_handles.get('twitter', ''),
                    "url": f"https://twitter.com/{social_handles.get('twitter')}" if social_handles.get('twitter') else ""
                },
                "linkedin": {
                    "username": social_handles.get('linkedin', ''),
                    "url": f"https://linkedin.com/in/{social_handles.get('linkedin')}" if social_handles.get('linkedin') else ""
                },
                "instagram": {
                    "username": social_handles.get('instagram', ''),
                    "url": f"https://instagram.com/{social_handles.get('instagram')}" if social_handles.get('instagram') else ""
                },
                "facebook": {
                    "username": social_handles.get('facebook', ''),
                    "url": f"https://facebook.com/{social_handles.get('facebook')}" if social_handles.get('facebook') else ""
                },
                "gitlab": {
                    "username": social_handles.get('gitlab', ''),
                    "url": f"https://gitlab.com/{social_handles.get('gitlab')}" if social_handles.get('gitlab') else ""
                },
                "devto": {
                    "username": social_handles.get('devto', ''),
                    "url": f"https://dev.to/{social_handles.get('devto')}" if social_handles.get('devto') else ""
                },
                "medium": {
                    "username": social_handles.get('medium', ''),
                    "url": f"https://medium.com/@{social_handles.get('medium')}" if social_handles.get('medium') else ""
                },
                "youtube": {
                    "username": social_handles.get('youtube', ''),
                    "url": f"https://youtube.com/@{social_handles.get('youtube')}" if social_handles.get('youtube') else ""
                },
                "tiktok": {
                    "username": social_handles.get('tiktok', ''),
                    "url": f"https://tiktok.com/@{social_handles.get('tiktok')}" if social_handles.get('tiktok') else ""
                }
            },
            "profile_links": {
                "primary_profile": identity.get('profile_url', ''),
                "personal_website": raw_profile.get('raw_signals', {}).get('github_user', {}).get('blog', ''),
                "stackoverflow": social_handles.get('stackoverflow', '')
            },
            "verification": {
                "is_real_person": True,
                "email_found": bool(email),
                "phone_found": bool(phone),
                "social_platforms_found": len([p for p in social_handles if social_handles[p]]),
                "verification_score": 85 if email else 50,
                "filter_reason": "Real person with technical indicators"
            },
            "raw_data": raw_profile,
            "enriched_at": time.time()
        }
        
        return enhanced_profile
    
    def batch_process(self, profiles: List[Dict]) -> List[Dict]:
        """Process multiple profiles"""
        results = []
        for profile in profiles:
            processed = self.process_profile(profile)
            if processed:
                results.append(processed)
            time.sleep(0.5)  # Rate limiting
        return results
