"""Explicit game-information searches: configured APIs, then Wikidata/Wikipedia.

All results are restricted to the selected console. No HTML is executed.
"""
from datetime import datetime, timezone
import json
import re
import urllib.parse

from . import cover_sources as api
from .cover_settings import load_settings, configured
from .cover_titles import clean_title, matching_indices
from .game_details import public_url, _text, synopsis

PLATFORMS = {'sms':{'Q209868'}, 'gg':{'Q751719'}, 'gb':{'Q186437'},
             'nes':{'Q172742'}, 'md':{'Q10676'}, 'snes':{'Q183259'},
             'ng':{'Q1054350','Q64428080','Q3338058'}}


def _json(url):
    return json.loads(api.request(url, 4*1024*1024,
        headers={'User-Agent':'RetroRecomp game cards (https://github.com/ArthurReboulSalze/RetroRecomp)'}))


def _wiki(**params):
    return _json('https://www.wikidata.org/w/api.php?'+urllib.parse.urlencode(
        dict(format='json',**params)))


def _values(entity, prop):
    return [c.get('mainsnak',{}).get('datavalue',{}).get('value')
            for c in entity.get('claims',{}).get(prop,[]) if c.get('rank')!='deprecated']


def _ids(entity, prop):
    return [v['id'] for v in _values(entity,prop) if isinstance(v,dict) and 'id' in v]


def _label(entity, language):
    labels=entity.get('labels',{})
    return next((labels[k]['value'] for k in (language,'en') if k in labels),'')


def wikidata(title, system, language):
    response=_wiki(action='wbsearchentities',search=clean_title(title),language=language,
                   uselang=language,limit=10,type='item')
    ids=[r['id'] for r in response.get('search',[]) if re.fullmatch('Q[0-9]+',r.get('id',''))]
    if not ids:return []
    entities=_wiki(action='wbgetentities',ids='|'.join(ids),props='labels|aliases|claims|sitelinks',
                   languages=language+'|en').get('entities',{})
    rows=[]
    for entity in entities.values():
        if not PLATFORMS[system].intersection(_ids(entity,'P400')):continue
        names=[v['value'] for v in entity.get('labels',{}).values()]
        names += [v['value'] for values in entity.get('aliases',{}).values() for v in values]
        if not matching_indices(names,title,title):continue
        rows.append(entity)
    ids=set()
    for row in rows:
        for prop in ('P178','P123','P136','P2664'):
            ids.update(_ids(row,prop))
    labels=_wiki(action='wbgetentities',ids='|'.join(sorted(ids)[:45]),props='labels',
                 languages=language+'|en').get('entities',{}) if ids else {}
    result=[]
    for row in rows:
        def names(prop):return ', '.join(filter(None,(_label(labels.get(q,{}),language) for q in _ids(row,prop))))
        dates=[]
        general=[]
        for claim in row.get('claims',{}).get('P577',[]):
            if claim.get('rank')=='deprecated':continue
            value=claim.get('mainsnak',{}).get('datavalue',{}).get('value',{})
            time=value.get('time','') if isinstance(value,dict) else ''
            precision=value.get('precision',9) if isinstance(value,dict) else 9
            if not re.match(r'^\+[0-9]{4}-[0-9]{2}-[0-9]{2}',time):continue
            date=time[1:11] if precision>=11 else time[1:8] if precision==10 else time[1:5]
            platforms={q.get('datavalue',{}).get('value',{}).get('id') for q in claim.get('qualifiers',{}).get('P400',[])}
            if platforms.intersection(PLATFORMS[system]):dates.append(date)
            elif not platforms:general.append(date)
        links=row.get('sitelinks',{})
        lang=language if language+'wiki' in links else 'en'
        page=links.get(lang+'wiki',{}).get('title','')
        record=dict(title=_label(row,language),developer=names('P178'),publisher=names('P123'),
            genre=names('P136'),players='',release=min(dates or general,default=''),
            release_scope='platform' if dates else 'general',provider='Wikidata / Wikipedia',
            source=f'https://www.wikidata.org/wiki/{row["id"]}',language=lang,description='',
            license='Wikidata: CC0',wiki_title=page,wiki_language=lang)
        result.append(record)
    return result


def _tgdb(title, system, account):
    if system not in api.TGDB_SYSTEMS:return []
    params=dict(apikey=account['apikey'],name=clean_title(title),
                **{'filter[platform]':api.TGDB_SYSTEMS[system],
                   'fields':'overview,players,developers,publishers,genres'})
    data=api._json('thegamesdb','https://api.thegamesdb.net/v1.1/Games/ByGameName?'+urllib.parse.urlencode(params))
    rows=[r for r in data.get('data',{}).get('games',[]) if r.get('platform')==api.TGDB_SYSTEMS[system]]
    result=[]
    for i in matching_indices([r.get('game_title','') for r in rows],title,title):
        row=rows[i]
        # Numeric lookup IDs are not displayed as human names.
        result.append(dict(title=row.get('game_title',''),release=row.get('release_date',''),
            release_scope='platform',players=str(row.get('players') or ''),description=row.get('overview',''),
            provider='TheGamesDB',source=f'https://thegamesdb.net/game.php?id={int(row["id"])}',language='en'))
    return result


def _igdb(title, system, account):
    if system not in api.IGDB_SLUGS:return []
    key=api.hashlib.sha256((account['client_id']+'\0'+account['client_secret']).encode()).hexdigest()
    token,expiry=api._tokens.get(key,('',0))
    if api.time.monotonic()>=expiry:
        body=urllib.parse.urlencode(dict(client_id=account['client_id'],client_secret=account['client_secret'],grant_type='client_credentials')).encode()
        data=api._json('igdb','https://id.twitch.tv/oauth2/token',body=body)
        token=data['access_token']
        api._tokens[key]=(token,api.time.monotonic()+max(0,int(data['expires_in'])-60))
    headers={'Client-ID':account['client_id'],'Authorization':'Bearer '+token,'Content-Type':'text/plain'}
    slug=api.IGDB_SLUGS[system]
    platforms=api._json('igdb','https://api.igdb.com/v4/platforms',body=f'fields id,slug; where slug = "{slug}"; limit 1;'.encode(),headers=headers)
    if not platforms or platforms[0].get('slug')!=slug:return []
    platform=int(platforms[0]['id'])
    query=('fields name,url,summary,storyline,platforms,genres.name,involved_companies.developer,'
           'involved_companies.publisher,involved_companies.company.name,release_dates.platform,release_dates.human; search '+
           json.dumps(clean_title(title))+f'; where platforms = ({platform}); limit 20;')
    rows=api._json('igdb','https://api.igdb.com/v4/games',body=query.encode(),headers=headers)
    rows=[r for r in rows if platform in r.get('platforms',[])]
    result=[]
    for i in matching_indices([r.get('name','') for r in rows],title,title):
        row=rows[i]
        companies=row.get('involved_companies',[])
        def names(role):return ', '.join(c.get('company',{}).get('name','') for c in companies if c.get(role))
        result.append(dict(title=row.get('name',''),source=public_url(row.get('url','')),
            provider='IGDB',language='en',developer=names('developer'),publisher=names('publisher'),
            genre=', '.join(g.get('name','') for g in row.get('genres',[])),
            release=', '.join(dict.fromkeys(r.get('human','') for r in row.get('release_dates',[]) if r.get('platform')==platform)),
            release_scope='platform',description=synopsis(row.get('summary') or row.get('storyline',''))))
    return result


def search(title, system, language, settings=None):
    settings=settings if settings is not None else load_settings()
    accounts=settings.get('accounts',{})
    # Existing API locks protect the common quota with artwork downloads.
    for provider, callback in (('igdb',_igdb),('thegamesdb',_tgdb)):
        if not configured(provider,accounts.get(provider,{})):continue
        try:
            with api._locks[provider]:rows=callback(title,system,accounts[provider])
            if rows:return rows
        except (ValueError, KeyError, TypeError, OSError):pass
    return wikidata(title,system,language)


def complete(record):
    """Only fetch article text for the chosen entity; preserve attribution."""
    result=dict(record)
    page=result.pop('wiki_title','')
    language=result.pop('wiki_language','en')
    if page and language in ('en','fr','de','it','es','ja','zh','ru'):
        params=dict(action='query',format='json',prop='extracts',exintro=1,explaintext=1,
                    exsentences=3,redirects=1,titles=page)
        try:
            data=_json(f'https://{language}.wikipedia.org/w/api.php?'+urllib.parse.urlencode(params))
            pages=data.get('query',{}).get('pages',{})
            extract=next((p.get('extract','') for p in pages.values() if p.get('extract')),'')
            if extract:
                result['description']=synopsis(extract)
                result['source']=f'https://{language}.wikipedia.org/wiki/'+urllib.parse.quote(page.replace(' ','_'))
                result['license']='Wikipedia: CC BY-SA 4.0 · Wikidata: CC0'
        except (ValueError, OSError, KeyError, TypeError):pass
    return result
