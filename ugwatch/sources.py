from urllib.parse import urlencode


def search_url(query):
    return 'https://www.bing.com/news/search?' + urlencode({'q':query,'format':'rss'})


SOURCES = [
    ('eGP • procurement notices','https://egpuganda.go.ug/bid-notices','egp','Official'),
    ('eGP • disposal notices','https://egpuganda.go.ug/disposal-notices','egp_disposal','Official'),
    ('Daily Monitor • tenders','https://www.monitor.co.ug/uganda/jobs/tenders','html','Newspapers'),
    ('New Vision • tenders','https://www.newvision.co.ug/opportunities/tenders','newvision_tenders','Newspapers'),
    ('New Vision • notices','https://www.newvision.co.ug/opportunities/notices','newvision_notices','Newspapers'),
    ('New Vision • business','https://www.newvision.co.ug/category/business?id=3','html','Newspapers'),
    ('PPDA • bid invitations','https://gpp.ppda.go.ug/public/bid-invitations','ppda','Official'),
    ('URA • tenders','https://ura.go.ug/en/opportunities/tenders/','html','Official'),
    ('KCCA • procurement','https://www.kcca.go.ug/tenders','html','Official'),
    ('NWSC • bids and tenders','https://www.nwsc.co.ug/notices-2/','html','Official'),
    ('Bank of Uganda • procurement','https://www.bou.or.ug/procurement','bou','Official'),
    ('World Bank • Uganda procurement','https://projects.worldbank.org/en/projects-operations/procurement?srce=both&project_ctry_name_exact=Uganda','worldbank','Official'),
    ('Ministry of Finance • procurement','https://www.finance.go.ug/media-center/procurement','html','Official'),
    ('NSSF • tenders','https://www.nssfug.org/opportunities/tenders/','html','Official'),
    ('UBOS • procurement','https://www.ubos.org/procurement/','html','Official'),
    ('UCC • tenders','https://www.ucc.co.ug/tenders/','html','Official'),
    ('Uganda Development Bank • procurement','https://www.udbl.co.ug/procurement-notices/','html','Official'),
    ('ERA • procurement','https://www.era.go.ug/procurement-tenders/','html','Official'),
    ('UEGCL • bids and tenders','https://uegcl.com/bids-and-tenders/','html','Official'),
    ('The Independent','https://www.independent.co.ug/feed/','rss','Newspapers'),
    ('Daily Monitor • news discovery',search_url('site:monitor.co.ug business'),'search','Discovery'),
    ('New Vision • news discovery',search_url('site:newvision.co.ug business'),'search','Discovery'),
    ('Uganda • auctions & property',search_url('Uganda ("public auction" OR "auction notice" OR "sale by auction")'),'search','Discovery'),
    ('Uganda • tenders & bids',search_url('Uganda (tender OR "bid notice" OR prequalification OR "expression of interest")'),'search','Discovery'),
    ('Uganda • grants & enterprise',search_url('Uganda ("business grant" OR "call for proposals" OR "investment opportunity" OR "business financing")'),'search','Discovery'),
    ('Uganda • business headlines',search_url('Uganda business economy trade investment'),'search','Discovery'),
]


def seed(db):
    # Bundled sources are matched by name so improved adapters/URLs reach existing
    # databases; enabled flags and collected notices are kept. Custom sources are untouched.
    for name,url,kind,group in SOURCES:
        row=db.execute("SELECT id,url,kind FROM sources WHERE name=? AND group_name<>'Custom'",(name,)).fetchone()
        if row is None:
            db.execute('INSERT OR IGNORE INTO sources(name,url,kind,group_name) VALUES (?,?,?,?)',(name,url,kind,group))
        elif (row['url'],row['kind'])!=(url,kind) and not db.execute('SELECT 1 FROM sources WHERE url=? AND id<>?',(url,row['id'])).fetchone():
            db.execute("UPDATE sources SET url=?,kind=?,group_name=?,status='Not checked',message='',last_good_count=0 WHERE id=?",(url,kind,group,row['id']))
