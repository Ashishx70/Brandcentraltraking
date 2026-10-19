from .ekart import EkartScraper
from .delhivery import DelhiveryScraper
from .bluedart import BlueDartScraper
from .xpressbees import XpressBeesScraper
from .shadowfax import ShadowfaxScraper

class ScraperFactory:
    @staticmethod
    def get_scraper(courier_name: str, awb: str = None):
        name = str(courier_name or "").lower().replace(" ", "").replace("-", "").replace("_", "")
        awb_clean = str(awb or "").upper().strip()

        # 1. Match by Courier Name (handles all spelling variations like XPESSBEES, SHADOFEX, DELIVERY)
        if any(k in name for k in ["ekart", "ekl", "myntra", "mysc"]):
            return EkartScraper()
        elif any(k in name for k in ["delhivery", "delivery", "dlv", "delh"]):
            return DelhiveryScraper()
        elif any(k in name for k in ["bluedart", "blue", "bdart"]):
            return BlueDartScraper()
        elif any(k in name for k in ["xpress", "xpess", "xpes", "xbees", "xb"]):
            return XpressBeesScraper()
        elif any(k in name for k in ["shadowfax", "shadofex", "shadofax", "shadow", "shado", "sf"]):
            return ShadowfaxScraper()

        # 2. Auto-detect by AWB length and starting prefix rules
        if awb_clean:
            awb_len = len(awb_clean)
            p2 = awb_clean[:2]

            # 1. BlueDart: Length 11, prefix in ('76', '65', '78', '82')
            if awb_len == 11 and p2 in ['76', '65', '78', '82']:
                return BlueDartScraper()

            # 2. Delhivery: 15 (21, 19), 13 (59, 48), 14 (59)
            if (awb_len == 15 and p2 in ['21', '19']) or \
               (awb_len == 13 and p2 in ['59', '48']) or \
               (awb_len == 14 and p2 == '59'):
                return DelhiveryScraper()

            # 3. Ekart: 14 (MY, FM)
            if awb_len == 14 and p2 in ['MY', 'FM']:
                return EkartScraper()

            # 4. Shadowfax: 14 (R2, R1), 15 (SF), 12 (R2), 13 (SF), 11 (RT)
            if (awb_len == 14 and p2 in ['R2', 'R1']) or \
               (awb_len == 15 and p2 == 'SF') or \
               (awb_len == 12 and p2 == 'R2') or \
               (awb_len == 13 and p2 == 'SF') or \
               (awb_len == 11 and p2 == 'RT'):
                return ShadowfaxScraper()

            # 5. Xpressbees: 13 (23), 14 (13)
            if (awb_len == 13 and p2 == '23') or \
               (awb_len == 14 and p2 == '13'):
                return XpressBeesScraper()

            # Secondary fallback for other prefixes
            if awb_clean.startswith("SF") or awb_clean.startswith("R"):
                return ShadowfaxScraper()
            elif awb_clean.startswith("19") and len(awb_clean) >= 12:
                return DelhiveryScraper()

        return None
