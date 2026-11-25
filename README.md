# Ipar4.0-Projekt

Python-szimuláció egy háromzónás üvegházi ágyás öntözéséhez. A kísérletben
egy közös szelep öntözi mindhárom zónát. A vezérlés az egyik futásban a 2. zóna
mérése, a másikban a három zóna méréseinek átlaga alapján dönt.

## Talajmodell

Az `advance_hour` egy szimulált órányi vízveszteséget és a közös szelep parancsát
alkalmazza. A visszaadott állapotból kiolvasható a zónák vízkészlete milliméterben
és a relatív modellnedvesség százalékban. A lépés külön visszaadja a kijuttatott
vízmennyiséget literben.

```python
from soil_model import SoilState, advance_hour

state = SoilState()
step = advance_hour(state, valve_open=True)
print(step.state.water_mm)  # (19.77, 19.76, 19.7)
print(step.applied_water_l)  # 6.0
```

A 168 órás futás 07:00-kor kezdődik. Minden zóna 1 m² területű, 18 mm vízzel
indul, és legfeljebb 30 mm-t tárol. A nappali alapveszteség zónánként
0,23 / 0,24 / 0,30 mm/óra, az éjszakai veszteség 0,04 / 0,04 / 0,05 mm/óra.
A hétnapos időjárási profil csak a nappali veszteséget módosítja. Egy nyitási
parancs 2 mm vizet juttat minden zónára, vagyis összesen 6 litert. A készletet a
modell 0 és 30 mm között tartja, és minden órában 0,0001 mm felbontásra
kerekíti. A teljes kijuttatott víz beleszámít a vízfogyasztásba akkor is, ha
egy zóna eléri a tárolási határát. A számok
szimulációs paraméterek, növény- és talajspecifikus kalibrálás nélkül.

## Ellenőrzés

A modell a Python standard könyvtárát használja. A tesztek a repó gyökeréből
futtathatók.

```bash
python3 -m unittest discover -v
```

A tesztek ellenőrzik a vízmérleget, az időjárási profil alkalmazását, a
tárolási határokat és a két öntözési stratégia teljes heti eredményét az 50%-os
és 55%-os indítási küszöbnél. A céltartomány a tesztekben 40–75% relatív
modellnedvesség.
