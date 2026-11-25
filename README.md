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

## MQTT-adatút

Futtatáshoz Python 3.9 vagy újabb és egy helyi Mosquitto broker kell. A repó
gyökeréből telepítsd a Python-függőséget. Windowson a `python3` helyett a `py`
parancsot használhatod.

```bash
python3 -m pip install -r requirements.txt
```

Indítsd el a Mosquittót `mosquitto -p 1883` paranccsal. Dockerrel ugyanez egy
külön terminálban így futtatható.

```bash
docker run --rm -p 127.0.0.1:1883:1883 eclipse-mosquitto:2 mosquitto -c /mosquitto-no-auth.conf
```

Egy másik terminálban indítsd el a vezérlőt. Ha megjelent a `Listening on`
üzenet, indítható a szimulátor.

```bash
python3 -m controller --threshold 50
```

Egy harmadik terminálban futtasd le a két változatot.

```bash
python3 -m simulator --mode single --output single.csv
python3 -m simulator --mode average --output average.csv
```

A szimulátor az `irrigation/measurement` témára publikálja az eltelt órát,
a futásazonosítót és a `moisture_percent` méréseket. Egypontos módban csak a
2. zóna mérését küldi, hárompontos módban mindháromét. A vezérlő az
`irrigation/command` témára küldi vissza a futásazonosítót, az órát, a döntéshez
használt nedvességet és a `valve_open` parancsot. A szelep akkor nyit, ha a
döntési érték a küszöb alatt van. A szimulátor a futáshoz és az éppen várt órához
tartozó első érvényes parancsra lép tovább. Ha 5 másodpercen belül nem érkezik
hozzá ilyen parancs, a futás hibával véget ér. A CSV óránként rögzíti a döntést,
a kijuttatott litereket és mindhárom zóna állapotát az öntözési lépés előtt és után.

Kétórás demóhoz indítsd az egypontos szimulációt szárazabb 2. zónával.

```bash
python3 -m simulator --mode single --hours 2 --initial-water-mm 18 14.5 18 --output demo.csv
```

Az első sorban a szelep nyit, 6 liter kerül az ágyásra, a következő órában
pedig a 2. zóna már a küszöb felett van. Az 55%-os heti összehasonlításhoz
állítsd le a futó vezérlőt, és indítsd újra a `--threshold 55` kapcsolóval.

## Ellenőrzés

A tesztek a függőség telepítése után, a repó gyökeréből futtathatók.

```bash
python3 -m unittest discover -v
```

A tesztek ellenőrzik a vízmérleget, az időjárási profil alkalmazását, a
tárolási határokat és a két öntözési stratégia teljes heti eredményét az 50%-os
és 55%-os indítási küszöbnél. A céltartomány a tesztekben 40–75% relatív
modellnedvesség.

A teljes MQTT-integrációs teszthez csak a broker fusson. A teszt maga indítja
a vezérlőt és a szimulátort. Linuxon és macOS-en így adható meg a broker portja.

```bash
MQTT_TEST_PORT=1883 python3 -m unittest discover -v
```

PowerShellben a port beállítása külön parancs.

```powershell
$env:MQTT_TEST_PORT = '1883'
py -m unittest discover -v
```
