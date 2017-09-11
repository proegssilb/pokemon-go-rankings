#!/usr/bin/env python3

import asyncio
import aiohttp
import atexit
import demjson
import os.path
from functools import partial, reduce
from operator import itemgetter
from pprint import pprint
import jinja2


loop = asyncio.get_event_loop()
session = aiohttp.ClientSession(loop=loop)
atexit.register(lambda: session.close())


def getPokemonStats(num, pokedata, tiers, imgUrl):
    """Calculate the ranking data.

    Data returned includes (as a dictionary):
    - max attack/defense/stam/cp
    - tier placement
    - name
    - previous evolutions
    - image URL

    Arguments:
    num -- The pokemon number relevant. 1-251.
    pokedata -- Deserialized JSON from pokemongo-data-normalizer
    tiers -- The tier config, as from config.json.
    """  # noqa
    pokeDatum = pokedata[num-1]
    # CPM Source: https://github.com/mathiasbynens/pogocpm2level/blob/master/pogocpm2level/cpm2level.py  # noqa
    cpMultiplier = 0.79030001
    maxStam = (15+pokeDatum['stats']['baseStamina']) * cpMultiplier
    maxAtt = (15+pokeDatum['stats']['baseAttack']) * cpMultiplier
    maxDef = (15+pokeDatum['stats']['baseDefense']) * cpMultiplier
    maxCp = int((maxStam**0.5) * maxAtt * (maxDef**0.5)/10)
    rv = {'name': pokeDatum['name'],
          'atk': pokeDatum['stats']['baseAttack'],
          'stam': pokeDatum['stats']['baseStamina'],
          'def': pokeDatum['stats']['baseDefense'],
          'cp': maxCp,
          'id': pokeDatum['id'],
          'num': num,
          'imgUrl': imgUrl.format(num),
          'prevolution': pokeDatum.get('pastEvolutions', []),
          'rarity': pokeDatum.get('rarity', {'name': 'Common'})['name']}
    for idx, prevo in enumerate(rv['prevolution']):
        fil = filter(lambda p: p[1]['id'] == prevo['id'], enumerate(pokedata))
        num, prevo = list(fil)[0]
        rv['prevolution'][idx] = num+1
    for tierName, tierData in tiers.items():
        for criteria in tierData['search']:
            fieldName = criteria['field']
            fieldMin = criteria['min'] if 'min' in criteria else 0
            fieldMax = criteria['max'] if 'max' in criteria else 99999999999999
            if not (fieldMin <= rv[fieldName] < fieldMax):
                break
        else:
            rv['tier'] = tierName
    return rv


async def getResource(url):
    """Return parsed resource requested."""
    async with session.get(url) as response:
        if url.endswith('.json'):
            data = await response.text()
            return demjson.decode(data)
        elif url.endswith('.js'):
            data = await response.text()
            if '=' in data:
                idx = data.index('=')+1
                data = data[idx:]
                idx = data.index(';')
                data = data[:idx]
            return demjson.decode(data)
        else:
            return await response.text()


def calcStats(config, pokedata):
    mapfunc = partial(getPokemonStats, pokedata=pokedata,
                      tiers=config['tiers'], imgUrl=config['imgsPattern'])
    rawStats = [mapfunc(i) for i in range(1, 251)]
    maxStam = reduce(lambda x, y: max(x, y['stam']), rawStats, 0)
    maxDef = reduce(lambda x, y: max(x, y['def']), rawStats, 0)
    maxAtk = reduce(lambda x, y: max(x, y['atk']), rawStats, 0)
    return rawStats, maxStam, maxAtk, maxDef


async def main():
    config = demjson.decode_file('./data/config.json')
    pokedata = await getResource(config['pokemonStats'])
    rawStats, maxStam, maxAtk, maxDef = calcStats(config, pokedata)

    res = config['tiers'].copy()
    for tierName in res:
        iterable = filter(lambda p: p.get('tier', '') == tierName, rawStats)
        for sortInfo in reversed(config['tiers'][tierName]['sort']):
            keyfunc = itemgetter(sortInfo['field'])
            rev = sortInfo['dir'] == 'desc'
            iterable = sorted(iterable, key=keyfunc, reverse=rev)
        res[tierName] = list(iterable)

    tiersOrdered = [(tierData['order'], tierName) for (tierName, tierData) in
                    config['tiers'].items()]
    tiersOrdered.sort()

    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(os.path.join(os.path.curdir, 'data')),
        autoescape=True
    )
    statLimits = {'atk': maxAtk, 'def': maxDef, 'stam': maxStam}
    template = env.get_template('template.html')
    with open('index.html', 'w', encoding='utf-8') as outputFile:
        outputFile.write(template.render(tiersOrdered=tiersOrdered,
                                         tierData=res,
                                         config=config,
                                         statLimits=statLimits))

if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
