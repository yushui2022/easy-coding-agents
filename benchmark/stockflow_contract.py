"""Independent acceptance tests; opt-in via STOCKFLOW_PROJECT, outside app root."""
from concurrent.futures import ThreadPoolExecutor
import csv
import io
import os
from pathlib import Path
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.environ['STOCKFLOW_PROJECT'])
from stockflow.main import create_app

KEYS = {'acceptance-admin':'admin', 'acceptance-viewer':'viewer'}
ADMIN = {'X-API-Key':'acceptance-admin'}
VIEWER = {'X-API-Key':'acceptance-viewer'}


@pytest.fixture
def clients(tmp_path):
    path = str(tmp_path/'db.sqlite')
    with TestClient(create_app(path, KEYS)) as first, TestClient(create_app(path, KEYS)) as second:
        yield first, second, path


def product(client, sku='SKU', stock=10, price=125, name='Example'):
    response = client.post('/products', headers=ADMIN, json=dict(sku=sku,name=name,stock=stock,price_cents=price))
    assert response.status_code == 201, response.text
    return response.json()


def order(client, pid, quantity=1, key='key', **extra):
    return client.post('/orders', headers={**ADMIN,'Idempotency-Key':key},
        json=dict(customer='Buyer',items=[dict(product_id=pid,quantity=quantity)],**extra))


def stock(client, pid):
    response = client.get(f'/products/{pid}',headers=ADMIN)
    assert response.status_code==200, response.text
    return response.json()['stock']


def test_health_and_openapi(clients):
    client, _, _ = clients
    assert client.get('/health').json()['status']=='ok'
    assert '/orders' in client.get('/openapi.json').json()['paths']


@pytest.mark.parametrize('path',['/products','/orders','/audit','/reports/summary','/export/products.csv','/products/1','/orders/1'])
def test_reads_require_key(clients,path):
    client, _, _ = clients
    assert client.get(path).status_code==401
    assert client.get(path,headers={'X-API-Key':'wrong'}).status_code==401


def test_viewer_cannot_write(clients):
    c,_,_=clients
    p=product(c)
    o=order(c,p['id']).json()
    writes=[('post','/products',dict(sku='NEW',name='X',stock=0,price_cents=0)),
        ('patch',f"/products/{p['id']}",dict(expected_version=2,name='change')),
        ('post','/inventory/adjustments',dict(product_id=p['id'],delta=1,reason='x')),
        ('post','/orders',dict(customer='X',items=[dict(product_id=p['id'],quantity=1)])),
        ('post',f"/orders/{o['id']}/cancel",None)]
    for method,path,body in writes:
        r=getattr(c,method)(path,headers={**VIEWER,'Idempotency-Key':'viewer'},json=body)
        assert r.status_code==403,(path,r.text)
    for path in ['/products','/orders','/audit','/reports/summary','/export/products.csv']:
        assert c.get(path,headers=VIEWER).status_code==200


@pytest.mark.parametrize('field,value',[('stock',-1),('stock',True),('stock',1.5),('price_cents',-1),('price_cents',False),('price_cents',1.2),('sku','  '),('name',' '),('extra',1)])
def test_product_validation(clients,field,value):
    c,_,_=clients
    payload=dict(sku='SKU',name='X',stock=0,price_cents=10)
    payload[field]=value
    assert c.post('/products',headers=ADMIN,json=payload).status_code==422
    assert c.get('/products',headers=ADMIN).json()['total']==0


def test_catalog_pagination_search_and_unique(clients):
    c,_,_=clients
    p=product(c,sku=' A ',name='  Alpha  ')
    assert (p['sku'],p['name'],p['version'])==('A','Alpha',1)
    product(c,sku='B',name='Beta')
    duplicate=c.post('/products',headers=ADMIN,json=dict(sku='A',name='Other',stock=2,price_cents=3))
    assert duplicate.status_code==409
    page=c.get('/products?limit=1&offset=1',headers=ADMIN).json()
    assert page['total']==2 and len(page['items'])==1 and page['items'][0]['sku']=='B'
    assert c.get('/products?q=alp',headers=ADMIN).json()['total']==1
    assert c.get('/products',headers=ADMIN,params={'q':"' OR 1=1 --"}).json()['total']==0


@pytest.mark.parametrize('query',['limit=0','limit=101','offset=-1'])
def test_pagination_validation(clients,query):
    c,_,_=clients
    for path in ['/products','/orders','/audit']:
        assert c.get(path+'?'+query,headers=ADMIN).status_code==422


def test_optimistic_version(clients):
    c,_,_=clients
    p=product(c)
    r=c.patch(f"/products/{p['id']}",headers=ADMIN,json=dict(expected_version=1,name='New',price_cents=99))
    assert r.status_code==200,r.text
    assert r.json()['version']==2
    assert c.patch(f"/products/{p['id']}",headers=ADMIN,json=dict(expected_version=1,name='Lost')).status_code==409
    assert c.patch(f"/products/{p['id']}",headers=ADMIN,json=dict(expected_version=2,stock=999)).status_code==422


def test_adjustment_atomicity_and_audit(clients):
    c,_,_=clients
    p=product(c,stock=2)
    for delta,status in [(3,201),(-6,409),(0,422),(True,422)]:
        r=c.post('/inventory/adjustments',headers=ADMIN,json=dict(product_id=p['id'],delta=delta,reason='count'))
        assert r.status_code==status,r.text
    assert stock(c,p['id'])==5
    actions=[a['action'] for a in c.get('/audit',headers=ADMIN).json()['items']]
    assert actions.count('stock_adjusted')==1


@pytest.mark.parametrize('quantity',[0,-1,True,1.5])
def test_order_quantity_validation(clients,quantity):
    c,_,_=clients
    p=product(c)
    assert order(c,p['id'],quantity).status_code==422
    assert stock(c,p['id'])==10


def test_required_idempotency_and_duplicate_lines(clients):
    c,_,_=clients
    p=product(c)
    body=dict(customer='B',items=[dict(product_id=p['id'],quantity=1)])
    assert c.post('/orders',headers=ADMIN,json=body).status_code==400
    assert c.post('/orders',headers={**ADMIN,'Idempotency-Key':' '},json=body).status_code==400
    body['items']*=2
    assert c.post('/orders',headers={**ADMIN,'Idempotency-Key':'d'},json=body).status_code==422


def test_multiline_failure_rollback_and_retry(clients):
    c,_,_=clients
    a,b=product(c,sku='A',stock=5),product(c,sku='B',stock=0)
    body=dict(customer='B',items=[dict(product_id=a['id'],quantity=3),dict(product_id=b['id'],quantity=1)])
    r=c.post('/orders',headers={**ADMIN,'Idempotency-Key':'retry'},json=body)
    assert r.status_code==409,r.text
    assert stock(c,a['id'])==5
    assert c.get('/orders',headers=ADMIN).json()['total']==0
    c.post('/inventory/adjustments',headers=ADMIN,json=dict(product_id=b['id'],delta=1,reason='new'))
    r=c.post('/orders',headers={**ADMIN,'Idempotency-Key':'retry'},json=body)
    assert r.status_code==201,r.text
    assert stock(c,a['id'])==2 and stock(c,b['id'])==0


def test_idempotency_snapshot_persistence_and_cancel(clients):
    c,second,path=clients
    p=product(c,stock=5,price=125)
    first=order(c,p['id'],2)
    assert first.status_code==201,first.text
    oid=first.json()['id']
    replay=order(second,p['id'],2)
    assert replay.status_code==200 and replay.json()['id']==oid
    assert order(second,p['id'],1).status_code==409
    assert stock(c,p['id'])==3
    current=c.get(f"/products/{p['id']}",headers=ADMIN).json()
    c.patch(f"/products/{p['id']}",headers=ADMIN,json=dict(expected_version=current['version'],price_cents=999))
    with TestClient(create_app(path,KEYS)) as reopened:
        assert order(reopened,p['id'],2).json()['id']==oid
        saved=reopened.get(f'/orders/{oid}',headers=ADMIN).json()
        assert saved['total_cents']==250 and saved['items'][0]['unit_price_cents']==125
        for _ in range(2):
            assert reopened.post(f'/orders/{oid}/cancel',headers=ADMIN).json()['status']=='cancelled'
    assert stock(c,p['id'])==5
    summary=c.get('/reports/summary',headers=ADMIN).json()
    assert summary==dict(products=1,stock_units=5,confirmed_orders=0,revenue_cents=0)
    actions=[a['action'] for a in c.get('/audit?limit=100',headers=ADMIN).json()['items']]
    assert actions.count('order_created')==1 and actions.count('order_cancelled')==1


def test_concurrent_orders_cannot_oversell(clients):
    c,other,_=clients
    p=product(c,stock=5)
    with ThreadPoolExecutor(max_workers=12) as pool:
        responses=list(pool.map(lambda i:order(c if i%2 else other,p['id'],1,key=f'parallel-{i}'),range(16)))
    assert sorted(r.status_code for r in responses)==[201]*5+[409]*11
    assert stock(c,p['id'])==0
    assert c.get('/orders',headers=ADMIN).json()['total']==5


def test_concurrent_idempotency_and_cancel(clients):
    c,other,_=clients
    p=product(c,stock=10)
    with ThreadPoolExecutor(max_workers=8) as pool:
        responses=list(pool.map(lambda i:order(c if i%2 else other,p['id'],2,key='same'),range(8)))
    assert sorted(r.status_code for r in responses)==[200]*7+[201]
    ids={r.json()['id'] for r in responses}
    assert len(ids)==1 and stock(c,p['id'])==8
    oid=ids.pop()
    with ThreadPoolExecutor(max_workers=8) as pool:
        responses=list(pool.map(lambda i:(c if i%2 else other).post(f'/orders/{oid}/cancel',headers=ADMIN),range(8)))
    assert all(r.status_code==200 for r in responses)
    assert stock(c,p['id'])==10


def test_summary_and_csv_escaping(clients):
    c,_,_=clients
    p=product(c,sku='=SUM(1,2)',name='@bad,"quote"',stock=4,price=31)
    order(c,p['id'],3)
    assert c.get('/reports/summary',headers=ADMIN).json()==dict(products=1,stock_units=1,confirmed_orders=1,revenue_cents=93)
    response=c.get('/export/products.csv',headers=VIEWER)
    assert 'text/csv' in response.headers['content-type']
    row=list(csv.DictReader(io.StringIO(response.text)))[0]
    assert row['sku']=="'=SUM(1,2)" and row['name']=="'@bad,\"quote\""
    assert row['stock']=='1'


def test_missing_entities(clients):
    c,_,_=clients
    assert c.get('/products/999',headers=ADMIN).status_code==404
    assert c.get('/orders/999',headers=ADMIN).status_code==404
    assert c.post('/orders/999/cancel',headers=ADMIN).status_code==404
    assert order(c,999).status_code==404


def test_database_isolation(clients,tmp_path):
    c,_,_=clients
    product(c)
    with TestClient(create_app(str(tmp_path/'other.sqlite'),KEYS)) as isolated:
        assert isolated.get('/products',headers=ADMIN).json()['total']==0
