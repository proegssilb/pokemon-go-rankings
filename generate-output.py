#!/usr/bin/env python3

import asyncio
import aiohttp
import atexit
import demjson
import os.path
from functools import partial
from pprint import pprint
import jinja2


loop = asyncio.get_event_loop()
session = aiohttp.ClientSession(loop=loop)
atexit.register(lambda: session.close())


def getPokemonStats(num, pokelist, pokedata, tiers):
    """Calculate the ranking data.

    Data returned includes (as a dictionary):
    - max attack/defense/stam/cp
    - tier placement
    - name

    Arguments:
    num -- The pokemon number relevant. 1-251.
    pokelist -- Deserialized contents of URL named 'pokemonList'
    pokedata -- Deserialized contents of URL named 'pokemonStats'
    tiers -- The tier config, as from config.json.

    >>> pkl = [{ id: '1', num: '001', name: 'Bulbasaur', img: 'http://www.serebii.net/pokemongo/pokemon/001.png', type: 'Grass / Poison', height: '0.71 m', weight: '6.9 kg', candy: '25 Bulbasaur Candy', egg: '2 km' }, { id: '2', num: '002', name: 'Ivysaur', img: 'http://www.serebii.net/pokemongo/pokemon/002.png', type: 'Grass / Poison', height: '0.99 m', weight: '13.0 kg', candy: '100 Bulbasaur Candy', egg: 'Not in Eggs' }]
    >>> pkd = [ { "AnimTime": "6d56d53fdaac2a3f6d56d53f93a9ea3f0000000036ab0a403333b33fbfbbbb3f", "AttackTimerS": 29, "BaseAttack": 118, "BaseCaptureRate": 0.1599999964237213, "BaseDefense": 118, "BaseFleeRate": 0.10000000149011612, "BaseStamina": 90, "CandyToEvolve": 25, "CinematicMoves": "5a3b76", "CollisionHeadRadiusM": 0.27250000834465027, "CollisionHeightM": 0.6539999842643738, "CollisionRadiusM": 0.3815000057220459, "Evolution": 2, "EvolutionPips": "HoloPokemonClass.POKEMON_CLASS_NORMAL", "FamilyId": "HoloPokemonFamilyId.V0001_FAMILY_BULBASAUR", "HeightStdDev": 0.08749999850988388, "JumpTimeS": 1.149999976158142, "MovementTimerS": 10, "MovementType": "HoloPokemonMovementType.POKEMON_ENC_MOVEMENT_JUMP", "id": 1, "PokedexHeightM": 0.699999988079071, "PokedexWeightKg": 6.900000095367432, "PokemonClass": 1, "QuickMoves": "d601dd01", "Type1": "HoloPokemonType.POKEMON_TYPE_GRASS", "Type2": "HoloPokemonType.POKEMON_TYPE_POISON", "WeightStdDev": 0.862500011920929 }, { "AnimTime": "36ab2a40daac2a3f6d56d53f36ab0a4000000000000000406d56d53fdbdddd3f", "AttackTimerS": 8, "BaseAttack": 151, "BaseCaptureRate": 0.07999999821186066, "BaseDefense": 151, "BaseFleeRate": 0.07000000029802322, "BaseStamina": 120, "CandyToEvolve": 100, "CinematicMoves": "5a7476", "CollisionHeadRadiusM": 0.2549999952316284, "CollisionHeightM": 0.637499988079071, "CollisionRadiusM": 0.3187499940395355, "Evolution": 3, "EvolutionPips": "HoloPokemonClass.POKEMON_CLASS_NORMAL", "FamilyId": "HoloPokemonFamilyId.V0001_FAMILY_BULBASAUR", "HeightStdDev": 0.125, "JumpTimeS": 1.5, "MovementTimerS": 23, "MovementType": "HoloPokemonMovementType.POKEMON_ENC_MOVEMENT_JUMP", "id": 2, "PokedexHeightM": 1, "PokedexWeightKg": 13, "PokemonClass": 1, "QuickMoves": "d701d601", "Type1": "HoloPokemonType.POKEMON_TYPE_GRASS", "Type2": "HoloPokemonType.POKEMON_TYPE_POISON", "WeightStdDev": 1.625 }]
    >>> tcfg = {'bogusTier1': {'order': 1, 'search': [{"field": "cp", "max": 1500, "min": 0}]}}
    >>> getPokemonStats(1, pkl, pkd, tcfg)
    {'name': 'Bulbasaur', 'atk': 118, 'def': 118, '90', 'cp': 981, 'id': 1, 'tier': 'bogusTier1', 'evolution': 2}
    """  # noqa
    pokeItem, pokeDatum = pokelist[num-1], pokedata[num-1]
    if 'Number' not in pokeItem:
        print(num, pokeItem)
    if not (int(pokeItem['Number']) == num and pokeDatum['id'] == num):
        print('Failed to load correct data.')
        print('pokelist entry:', pokeItem)
        print()
        print('pokestats entry:', pokeDatum)
        exit()
    cpMultiplier = 0.7902  # Yes, it's arbitrary, but it seems to work.
    maxStam = (15+pokeDatum['BaseStamina']) * cpMultiplier
    maxAtt = (15+pokeDatum['BaseAttack']) * cpMultiplier
    maxDef = (15+pokeDatum['BaseDefense']) * cpMultiplier
    maxCp = int((maxStam**0.5) * maxAtt * (maxDef**0.5)/10)
    rv = {'name': pokeItem['Name'], 'atk': pokeDatum['BaseAttack'],
          'def': pokeDatum['BaseDefense'], 'cp': maxCp, 'id': pokeDatum['id'],
          'prevolution': pokeItem.get('Previous evolution(s)', [])}
    rv['prevolution'] = [p['Number'] for p in rv['prevolution']]
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


async def main():
    config = demjson.decode_file('./data/config.json')
    pokelist = demjson.decode_file('.\\data\\pokedex.json')
    pokedata = await getResource(config['pokemonStats'])
    mapfunc = partial(getPokemonStats, pokelist=pokelist, pokedata=pokedata,
                      tiers=config['tiers'])
    rawStats = [mapfunc(i) for i in range(1, 251)]

    res = config['tiers'].copy()
    for tierName in res:
        res[tierName] = list(filter(lambda p: p.get('tier', '') == tierName,
                                    rawStats))

    tiersOrdered = [(tierData['order'], tierName) for (tierName, tierData) in
                    config['tiers'].items()]
    tiersOrdered.sort()

    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(os.path.join(os.path.curdir, 'data')),
        autoescape=True
    )
    template = env.get_template('template.html')
    with open('pokemon-go-tiers.html', 'w', encoding='utf-8') as outputFile:
        outputFile.write(template.render(tiersOrdered=tiersOrdered,
                                         tierData=res))

if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
