"""What a notice is about: its category, whether it sells assets, which assets, and where.

Disposal of public assets (and any other asset sale) is the app's top priority, so these
rules are shared by every source, saved-page imports and the PDF reader.
"""
import re

CATEGORIES = ('Tender','Auction','Bid','Grant','Public notice','Business','Job')

# Every Ugandan government advert cites the law or the unit that runs procurement *and
# disposal*; that boilerplate says nothing about selling assets, so it is removed first.
BOILERPLATE = re.compile(
    r'public procurement and disposal of public assets(?: \(amendment\))?(?: act| regulations| authority)?|'
    r'procurement\s*(?:and|&)\s*disposal (?:of public assets )?(?:unit|entity|entities|committee|department|section|office|act|regulations)|'
    r'disposal of public assets (?:act|regulations|authority)|\bppda\b|\bpdu\b|\bpde\b',re.I)

ASSET_DISPOSAL = re.compile(
    r'\bauction(?:s|ing|eers?)?\b|\bdisposals?\b|\bdispose\b|sale by (?:public )?(?:auction|tender)|'
    r'sale of (?:used|old|obsolete|scrap|unserviceable|boarded|assorted|decommissioned|motor|vehicles?|assets?|'
    r'equipment|furniture|property|properties|land|livestock|farm animals|timber|trees)|'
    r'boarded[- ]off|board of survey|decommissioned assets?|\bscrap\b|unserviceable|obsolete (?:assets|items|stores|equipment)|'
    r'mortgage sale|bailiffs?\b|(?:invites?|invitation)[^.]{0,40}\bbids? for (?:the )?purchase|for sale by|private treaty',re.I)
WASTE_SERVICE = re.compile(r'(?:garbage|waste|refuse|sanitary|sewage|sludge|faecal|medical waste|effluent)[^.]{0,40}dispos|'
                           r'dispos\w*[^.]{0,25}(?:garbage|waste|refuse|sewage|sludge)',re.I)
# Central-bank and other financial "auctions" are not asset sales, wherever the words appear.
FINANCIAL = re.compile(r'treasury (?:bonds?|bills?)|t-?bills?\b|government securities|\bforex auction|foreign exchange auction|'
                       r'spectrum auction|repo auction',re.I)
STRONG_SALE = re.compile(r'\bauction|scrap|boarded|decommissioned|sale of|for sale|bids? for (?:the )?purchase',re.I)


def is_asset_disposal(text):
    text = BOILERPLATE.sub(' ', text or '')
    if not ASSET_DISPOSAL.search(text) or FINANCIAL.search(text): return False
    # "Fumigation and garbage collection and disposal" is a service contract, unless it also sells assets.
    return not WASTE_SERVICE.search(text) or bool(STRONG_SALE.search(text))


def category(text):
    if is_asset_disposal(text): return 'Auction'
    text = BOILERPLATE.sub(' ', text or '')
    patterns = [('Grant',r'\bgrants?\b|call for proposals'),
                ('Tender',r'\btenders?\b|pre.?qualification|expression of interest'),
                ('Bid',r'\bbids?\b|\bbidding\b|\bprocurement\b'),
                ('Public notice',r'public notice|notice to the public'),
                ('Business',r'\bbusiness\b|\binvest\w*|\beconom\w*|\btrade\b|\bfinanc\w*|\bbank\w*|\benterprise\w*|\btax\b|\bexport\w*')]
    return next((name for name,rx in patterns if re.search(rx,text,re.I)),None)


ASSET_TYPES = (
    ('Vehicles',r'vehicles?|motor ?cycles?|motorbikes?|\bcars?\b|trucks?|lorr(?:y|ies)|pick-?ups?|\bbus(?:es)?\b|tractors?|station wagons?|'
                r'land ?cruisers?|toyota|nissan|isuzu|mitsubishi|tippers?|ambulances?|\breg(?:istration)?\.? no'),
    ('Land & buildings',r'\bland\b(?!\s*-?\s*cruiser)|\bplots?\b|propert(?:y|ies)|\bhouses?\b|\bblock \d+|\bfolio\b|\bacres?\b|hectares?|building for sale'),
    ('Equipment & ICT',r'computers?|laptops?|printers?|photocopiers?|equipment|machine(?:s|ry)?|generators?|\bups\b|servers?|'
                       r'air ?conditioners?|televisions?|projectors?|appliances?'),
    ('Furniture & fittings',r'furniture|chairs?|desks?|tables?|cabinets?|shelves|fittings'),
    ('Scrap & metal',r'scrap|metal|tyres|batter(?:y|ies)|cables?'),
    ('Livestock & produce',r'cattle|cows?|goats?|pigs?|sheep|farm animals|livestock|poultry|chickens?|produce|timber|trees|logs|maize|coffee'),
)
ASSET_RX = [(name,re.compile(rx,re.I)) for name,rx in ASSET_TYPES]

# Cities and districts that appear in disposal adverts (not every district of Uganda).
PLACES = ('Kampala','Wakiso','Mukono','Entebbe','Jinja','Mbale','Gulu','Lira','Mbarara','Masaka','Fort Portal','Kabale','Arua',
          'Soroti','Hoima','Masindi','Tororo','Busia','Iganga','Kasese','Moroto','Kitgum','Mubende','Mityana','Luwero','Kotido',
          'Bushenyi','Ntungamo','Rukungiri','Kisoro','Kabarole','Kamuli','Pallisa','Kumi','Nebbi','Adjumani','Moyo','Yumbe',
          'Koboko','Apac','Kiryandongo','Nakasongola','Kayunga','Buikwe','Mpigi','Kalangala','Rakai','Lyantonde','Sembabule',
          'Ibanda','Isingiro','Kiruhura','Kyenjojo','Kamwenge','Bundibugyo','Kagadi','Kibaale','Buliisa','Kalungu','Butambala',
          'Gomba','Kyotera','Namayingo','Bugiri','Mayuge','Kaliro','Buyende','Namutumba','Butaleja','Sironko','Kapchorwa','Bukwo',
          'Bududa','Katakwi','Amuria','Kaberamaido','Serere','Ngora','Bukedea','Abim','Kaabong','Napak','Nakapiripirit','Amudat',
          'Agago','Pader','Lamwo','Amuru','Nwoya','Omoro','Oyam','Kole','Dokolo','Alebtong','Otuke','Amolatar','Zombo','Maracha',
          'Nakaseke','Kiboga','Kyankwanzi','Kassanda','Rubirizi','Mitooma','Sheema','Buhweju','Kazo','Rubanda','Kanungu','Bweyogerere',
          'Kira','Nansana','Makindye','Kawempe','Nakawa','Rubaga','Lugazi','Njeru','Kakiri','Matugga')
PLACE_RX = re.compile(r'\b(' + '|'.join(re.escape(p) for p in PLACES) + r')\b', re.I)
PLACE_NAMES = {p.lower(): p for p in PLACES}


# Letterhead and office addresses ("Plot 37/45 Kampala Road", "P.O. Box 7120, Kampala") are not
# what is being sold or where; they are removed before looking for assets and places.
ADDRESS = re.compile(r'\bplot\s*(?:no\.?\s*)?[A-Z]{0,3}\d[\w/ ,&-]*?[A-Za-z .]{0,40}?\b(?:road|avenue|street|lane|close|drive|way|crescent|hill)\b'
                     r'|\bp\.?\s?o\.?\s*box\s*\d+[,\s]*[A-Za-z]*', re.I)


def asset_types(text):
    text = ADDRESS.sub(' ', text or '')
    return [name for name,rx in ASSET_RX if rx.search(text)]


def places(text):
    found = []
    for m in PLACE_RX.finditer(ADDRESS.sub(' ', text or '')):
        name = PLACE_NAMES[m.group(1).lower()]
        if name not in found: found.append(name)
    return found


STOPWORDS = set('the and for of to in on at by from with a an notice notices invitation bid bids tender tenders public '
                'abridged detailed advert re no supply delivery provision procurement disposal under open domestic'.split())


def title_tokens(title):
    """Significant words of a title, for spotting the same advert on several sources."""
    return frozenset(w for w in re.findall(r'[a-z0-9]{3,}', (title or '').lower()) if w not in STOPWORDS)
