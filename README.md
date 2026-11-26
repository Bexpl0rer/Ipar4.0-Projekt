# Ipar4.0-Projekt

Python-szimuláció háromzónás üvegházi ágyás közös öntözőszeleppel. A két
stratégia: a középső zóna mérése (single) és a három zóna méréseinek számtani
átlaga (average). A szimuláció determinisztikus fizikai modellt, reprodukálható
szenzorzajt és MQTT-alapú hiszterézises vezérlést használ.

## Talajmodell

A 168 órás futás 07:00-kor kezdődik, 2016 darab öt modellperces lépésből áll.
A program gyorsított szimuláció: nem vár öt valós percet a mérések között.
Minden zóna 1 m² területű, kezdetben 18 mm vizet tartalmaz, legfeljebb 30 mm-t
tárol. A százalékos nedvesség a modell tárolókapacitásához viszonyított
vízkészlet, nem kalibrált térfogati talajnedvesség.

Nappal (07:00–19:00) a zónák alapvesztesége 0,23 / 0,24 / 0,30 mm/óra,
éjjel 0,04 / 0,04 / 0,05 mm/óra. A nappali veszteséget a hétnapos időjárási
profil szorozza. Minden ötperces lépésben az óránkénti veszteség 1/12 része
vonódik le. A számítás 8 tizedesjegyre kerekít, a készlet 0–30 mm között marad.

A teljes ágyás rögzített térfogatárama 0,1 L/perc (6 L/óra), a víz egyenlően
oszlik meg a három zóna között. Egy nyitott szelepes lépés 5 percig tart,
0,5 L-t juttat az ágyásra (zónánként 1/6 mm). A teljes vízfogyasztás a
nyitvatartási idő percben és a térfogatáram szorzata. A kijuttatott víz akkor
is beleszámít, ha a talaj már nem tudja teljes egészében eltárolni.
Ezek szimulációs paraméterek, növény- és talajspecifikus kalibráció nélkül.

A mért nedvességhez zónánként egyenletes eloszlású véletlen hibát adunk
(alapértelmezetten ±0,5 százalékpont), 0–100% közé korlátozva. A zaj csak a
mérést érinti, a tényleges vízkészletet nem. Mindkét módban minden időpontban
mindhárom zónára generálunk zajt, ezért azonos seed esetén a zajsorozat
megegyezik (a határértékeknél a levágás eltérhet).

## MQTT és futtatás

Python 3.9 vagy újabb és egy helyi Mosquitto broker szükséges. A repó
gyökerében telepítsd a függőségeket:

```powershell
py -m pip install -r requirements.txt
```

Windows alatt, ha a Mosquitto szolgáltatás már fut, nem kell újabb brokert
indítani. Egy terminálban indítsd a vezérlőt:

```powershell
py -m controller --lower-threshold 50 --upper-threshold 60
```

A szelep kezdetben zárva van. A vezérlési érték az alsó küszöböt elérve vagy
alulmúlva nyitja, a felső küszöböt elérve vagy meghaladva zárja a szelepet.
A küszöbök között a korábban végrehajtott szelepállapot marad érvényben.
A vezérlő minden ötperces mérésre állapotparancsot küld, nyitott állapotban
az öntözés folyamatos marad a következő döntésig.

A Listening on üzenet után másik terminálban futtasd mindkét stratégiát:

```powershell
py -m simulator --mode single --seed 42 --noise-pp 0.5 --output single.csv
py -m simulator --mode average --seed 42 --noise-pp 0.5 --output average.csv
```

A szimulátor az irrigation/measurement témára publikálja az eltelt percet
(minute), a futásazonosítót, a korábban végrehajtott szelepállapotot
(valve_open) és a moisture_percent méréseket. Single módban csak a 2. zóna
adata kerül az MQTT-üzenetbe, average módban mindháromé. A vezérlő az
irrigation/command témára küldi a futásazonosítót, az eltelt percet, a döntési
értéket és a kívánt valve_open állapotot. A visszajelzett előző állapot miatt
a megismételt MQTT-mérések nem változtatják meg a döntést. A szimulátor
csak az adott futáshoz és időponthoz tartozó első érvényes parancsra lép
tovább; alapértelmezetten 5 valós másodperc után hibát jelez.

A CSV ötpercenként tárolja a valódi és zajos méréseket, az előző és új
szelepállapotot, az öntözési perceket, a litereket és a lépés utáni
nedvességet. A program a végén összesíti a nyitvatartási időt, a vízfogyasztást
és zónánként a szárazsági határ alatt eltöltött modellórákat. Az alapértelmezett
szárazsági határ 40%, külön állítható a --dry-threshold kapcsolóval; a
számítás az ötperces lépések elején mért valódi modellállapoton alapul,
így az időtartam ötperces felbontású közelítés.

Rövid, kétórás demonstráció szárazabb középső zónával:

```powershell
py -m simulator --mode single --hours 2 --initial-water-mm 18 14.5 18 --output demo.csv
```

A zaj kikapcsolható a --noise-pp 0 kapcsolóval. A korábbi --threshold
kapcsolót a --lower-threshold és --upper-threshold váltja fel.

## Tesztelés

```powershell
py -m unittest discover -v
```

A tesztek ellenőrzik az ötperces vízmérleget, az eredeti óránkénti ráták
megőrzését, a zajt, a tárolási határokat, a hiszterézist, a heti vezérlést
és a vízfogyasztást. Az integrációs teszthez csak a broker fusson, a
teszt saját vezérlőt és szimulátort indít:

```powershell
$env:MQTT_TEST_PORT = '1883'
py -m unittest discover -v
```

Linuxon/macOS-en a py helyett python3, a környezeti változó pedig
MQTT_TEST_PORT=1883 python3 -m unittest discover -v.
