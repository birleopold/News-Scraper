import pytest
from datetime import datetime,timedelta
from ugwatch.db import connect,upsert_notice,EAT
from ugwatch.collectors import extract_deadline,canonical,category,public_url,collect_feed,collect_egp
from ugwatch import service
from helpers import insert,JsonClient,start_fake_run,insert_job,MONITOR_PAGE


def test_asset_disposals_are_recognised_everywhere():
    from ugwatch.collectors import is_asset_disposal,mark_disposals,category
    sales=['Bidding Document for Auctioning of Decommissioned Assets on 9 May 2026','Bidding Document for Disposal of Bank Properties',
           'EMBASSY OF ICELAND - SALE OF TOYOTA LANDCRUISER 70 BY PUBLIC AUCTION','UNICEF UGANDA - SALE OF USED VEHICLES, FURNITURE AND EQUIPMENT',
           'Kyambogo University Invites Bids for Disposal of Farm Animals','Conversion of Decommissioned Assets into Scrap',
           'Mortgage sale of land at Kira','Invitation to bid for the purchase of boarded-off motor vehicles','Abridged Disposal Notice - Public Bidding']
    services=['Provision of Fumigation and Garbage Collection and Disposal','Sanitary Waste Handling and Disposal Services',
              'Treasury bond auction oversubscribed','Bank of Uganda T-bill auction results','Supply of office furniture']
    assert all(is_asset_disposal(t) for t in sales)
    assert not any(is_asset_disposal(t) for t in services)
    assert category('Notice of Best Evaluated Bidder for Disposal of Bank Properties')=='Auction'
    items=mark_disposals([dict(title='Bidding Document for Disposal of Bank Properties',category='Tender'),
                          dict(title='Garbage collection and disposal',category='Tender'),
                          dict(title='Driver needed to dispose of old files',category='Job')])
    assert [i['category'] for i in items]==['Auction','Tender','Job']


def test_disposals_page_counts_and_alerts(app,client):
    from ugwatch.alerts import notify_run
    path=app.config['DATABASE']
    run_id=start_fake_run(app)
    insert(app,url='https://x.example/sale',title='Disposal of boarded-off vehicles',category='Auction')
    insert(app,url='https://x.example/tender',title='Supply of computers')
    view=client.get('/api/notices?view=disposals&status=current').json
    assert view['total']==1 and view['items'][0]['url'].endswith('/sale')
    over=client.get('/api/overview').json
    assert over['stats']['disposals']==1 and over['latest_disposals'][0]['url'].endswith('/sale')
    sent=[]
    assert notify_run(path,run_id,sender=lambda *a:(sent.append(a),(True,'ok'))[1])==1  # default mode: disposals
    title,body,url=sent[0]
    assert title=='1 new disposal / auction' and 'boarded-off' in body and url.endswith('?view=disposals')


def test_egp_disposal_rows_with_relative_links():
    from ugwatch.collectors import collect_egp
    class Response:
        content=b'<input name="_token" value="t">'
        def raise_for_status(self):pass
        def json(self):return {'recordsFiltered':1,'data':[{'action_links':'<a href="/disposal/notice/277562/details">View</a>',
            'procuring_entity':'MPIGI-LG/DPB/2022-2023/00048 Mpigi District Local Government','Method_title':'Public Bidding Public Bidding',
            'disposal_details':'Photocopier...','published_date':'<span>2026-11-19</span>','deadline_date':'<span class="badge">2026-12-03 14:00</span>'}]}
    class Client:
        def get(self,url):return Response()
        def request(self,url,method,data):return Response()
    items,_=collect_egp(Client(),{'kind':'egp_disposal'})
    i=items[0]
    assert i['url']=='https://egpuganda.go.ug/disposal/notice/277562/details' and i['category']=='Auction'
    assert i['reference']=='MPIGI-LG/DPB/2022-2023/00048' and i['organization']=='Mpigi District Local Government'
    assert i['title']=='Disposal: Photocopier (Mpigi District Local Government)' and i['deadline']=='2026-12-03'
    assert i['excerpt']=='Mpigi District Local Government · Public Bidding'
