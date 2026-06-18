# -*- coding: utf-8 -*-
import sys, json, datetime
sys.path.insert(0,'tools/ozon-listing-webui')
sys.stdout.reconfigure(encoding='utf-8')
from backend.freight_ozon import FreightClient
from backend.app_service import AUTH_ROOT
from backend.store import Store

RUB_CNY=0.0927; MARGIN=0.30; PAY=0.004; AD=0.10; RET=0.03; LOSS=0.02; PACK=3.0; COMM=0.12
ratioFees=PAY+AD+RET+LOSS
def dims(w):
    if w<=1500: return 130,90,80
    if w<=3000: return 160,120,100
    if w<=4000: return 200,140,120
    return 360,300,200

fc=FreightClient(auth_dir=AUTH_ROOT)
st=Store()
offers=['gw-24v-2ah','gw-24v-4ah','gw-24v-8ah','gw-40v-4ah','gw-40v-5ah','gw-40v-6ah','gw-40v-8ah',
'gw-40v-15ah','gw-40v-26ah','gw-60v-4ah','gw-60v-5ah','gw-60v-8ah','gw-80v-4ah','gw-80v-5ah',
'gw-82v-4ah','gw-82v-5ah','gw-82v-8ah','gw-82v-7p2ah','gw-82v-4ah-film','gw-82v-5ah-tab']
out=[]
for off in offers:
    d=st.find_by_offer_id(off) if hasattr(st,'find_by_offer_id') else None
    if d is None:
        # fallback: 直接查
        import sqlite3
        con=sqlite3.connect(r'tools/ozon-listing-webui/data/products.db'); con.row_factory=sqlite3.Row
        d=dict(con.execute('SELECT * FROM drafts WHERE offer_id=?',(off,)).fetchone()); con.close()
    w=float(d['weight_g'] or 0); cost=float(d['cost_cny'] or 0)
    L,W,H=dims(w)
    q=fc.quote(weight_g=w,length_mm=L,width_mm=W,height_mm=H,price_cny=cost)
    ts=q.get('tariffs') or []; ci=q.get('cheapest_index')
    freight=None
    if ts and ci is not None and 0<=ci<len(ts):
        freight=float(ts[ci].get('price_cny') or 0)
    elif ts:
        freight=min(float(t.get('price_cny') or 9e9) for t in ts)
    if not freight:
        out.append((off,w,cost,None,None,None,'no_freight')); continue
    fixedBeforeShip=cost+PACK
    costBase=fixedBeforeShip+freight
    netCoef=1-COMM-ratioFees
    targetCny=costBase*(1+MARGIN)/netCoef
    lineCny=targetCny/0.8
    st.update_draft(int(d['id']),{'price':str(round(targetCny)),'old_price':str(round(lineCny))})
    out.append((off,w,cost,round(freight,1),round(targetCny),round(lineCny),'ok'))
fc.close(); st.close()
print(json.dumps(out,ensure_ascii=False))
