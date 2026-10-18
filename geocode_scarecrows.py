#!/usr/bin/env python3
"""Geocode Bow scarecrow stops with US Census Geocoder; optional OSM fallback.

No packages required. Results cached; inspect matches before routing.
"""
import argparse, csv, json, time, urllib.parse, urllib.request, urllib.error
from pathlib import Path

BASE = Path(__file__).resolve().parent

def request(url, user_agent):
    req = urllib.request.Request(url, headers={'User-Agent': user_agent, 'Accept':'application/json'})
    with urllib.request.urlopen(req, timeout=25) as response:
        return json.load(response)

def census(address, agent):
    params = urllib.parse.urlencode({'address':address, 'benchmark':'Public_AR_Current', 'format':'json'})
    data = request('https://geocoding.geo.census.gov/geocoder/geographies/onelineaddress?' + params, agent)
    matches = data.get('result', {}).get('addressMatches', [])
    if not matches: return None
    m = matches[0]
    p = m['coordinates']
    return {'lat':p['y'], 'lon':p['x'], 'matched_address':m.get('matchedAddress',''), 'source':'US Census', 'match_type':m.get('tigerLine',{}).get('side','')}

def nominatim(address, agent):
    params = urllib.parse.urlencode({'q':address,'format':'jsonv2','limit':1,'countrycodes':'us','addressdetails':1})
    data = request('https://nominatim.openstreetmap.org/search?' + params, agent)
    if not data: return None
    m = data[0]
    return {'lat':float(m['lat']), 'lon':float(m['lon']), 'matched_address':m.get('display_name',''), 'source':'OpenStreetMap Nominatim', 'match_type':m.get('type','')}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', default=str(BASE/'bow_scarecrow_google_my_maps.csv'))
    parser.add_argument('--osm-fallback', action='store_true', help='Explicitly opt into one-time public Nominatim fallback; read https://operations.osmfoundation.org/policies/nominatim/ first')
    parser.add_argument('--contact', help='Contact email for identifying Nominatim requests (required with --osm-fallback)')
    args = parser.parse_args()
    if args.osm_fallback and not args.contact: parser.error('--osm-fallback requires --contact')
    agent = 'BowScarecrowRoute/1.0 (personal one-time geocoding; contact: '+(args.contact or 'local-user')+')'
    cache_path = BASE/'geocode_cache.json'
    cache = json.loads(cache_path.read_text()) if cache_path.exists() else {}
    with open(args.input, newline='', encoding='utf-8-sig') as f:
        rows = list(csv.DictReader(f))
    if not rows: raise SystemExit('Input CSV is empty')
    print('CSV columns:', ', '.join(rows[0]))
    last_osm = 0
    output=[]
    for i, row in enumerate(rows, 1):
        address = (row.get('Address') or row.get('address') or '').strip()
        if not address: raise SystemExit('Missing Address in row '+str(i))
        key = address.lower()
        result = cache.get(key)
        if result is None:
            try: result = census(address, agent)
            except (urllib.error.URLError, TimeoutError, ValueError) as exc:
                print('Census error:', address, exc)
            if result is None and args.osm_fallback:
                time.sleep(max(0, 1.2-(time.monotonic()-last_osm)))
                last_osm = time.monotonic()
                try: result = nominatim(address, agent)
                except (urllib.error.URLError, TimeoutError, ValueError) as exc:
                    print('Nominatim error:', address, exc)
            cache[key] = result if result else {'unresolved':True}
            cache_path.write_text(json.dumps(cache, indent=2))
        if result and result.get('unresolved'): result = None
        # Only accept matches within broad Bow-area bounds; still review all pins manually.
        if result and not (43.05 <= result['lat'] <= 43.23 and -71.68 <= result['lon'] <= -71.39):
            print('OUTSIDE AREA:', address, result['matched_address'])
            result = None
        record = {'Stop':row.get('Stop',str(i)), 'Name':row.get('Name',f'Scarecrow {i:02}'), 'Address':address,
                  'Latitude':result['lat'] if result else '', 'Longitude':result['lon'] if result else '',
                  'Matched Address':result['matched_address'] if result else '', 'Source':result['source'] if result else '',
                  'Review':'CHECK LOCATION' if result else 'UNRESOLVED'}
        output.append(record)
        print(f"{i:02}: {'MATCH' if result else 'UNRESOLVED'}  {address}")
    with open(BASE/'scarecrows_geocoded.csv','w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=output[0].keys());w.writeheader();w.writerows(output)
    features=[{'type':'Feature','properties':{'stop':r['Stop'],'name':r['Name'],'address':r['Address'],'source':r['Source']},
               'geometry':{'type':'Point','coordinates':[float(r['Longitude']),float(r['Latitude'])]}}
              for r in output if r['Latitude']!='']
    (BASE/'scarecrows_geocoded.geojson').write_text(json.dumps({'type':'FeatureCollection','features':features},indent=2))
    print(f"\nResolved {len(features)}/{len(output)}. Review scarecrows_geocoded.csv and map positions before routing.")
    print('Geocoding attribution: US Census Bureau; if OSM used: © OpenStreetMap contributors (ODbL).')

if __name__ == '__main__': main()
