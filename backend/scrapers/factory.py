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

        # 2. Auto-detect by AWB format if courier name is missing or unknown
        if awb_clean:
            if awb_clean.startswith("SF") or awb_clean.startswith("R") or "AJI" in awb_clean or "MYE" in awb_clean:
                return ShadowfaxScraper()
            elif len(awb_clean) in [13, 14, 15] and (awb_clean.startswith("13") or awb_clean.startswith("14") or awb_clean.startswith("23")):
                return XpressBeesScraper()
            elif awb_clean.startswith("19") and len(awb_clean) >= 12:
                return DelhiveryScraper()
            elif len(awb_clean) in [9, 10, 11] and awb_clean.isdigit():
                return BlueDartScraper()

        return None
