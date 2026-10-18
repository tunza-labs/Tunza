#!/usr/bin/env python3
"""Deterministic compositional generator for the Tunza triage v2 dataset and sealed test.

Wording comes only from the code templates below (no model, no Jev, no TypeSafe, no clinical data).
Every label comes from Tunza's own decide() in lib/assessment.ts, called through a local esbuild bundle.

  python3 tools/tunza-train/gen_cases.py --seed 20261018 --out tools/tunza-train/data/v2

Outputs (in --out): triage-train.jsonl, triage-sealed.jsonl, families.json, manifest.json.
Row format matches data/triage-train.jsonl: {"intake": {...}, "answer": {"disposition", "danger_facts", "follow_up_question"}}.

Leakage design. Every story is built from a template family: a shape (connector pattern), a subject group,
one or two symptom groups, and optional frame pools (observation openers, connectors, context sentences).
Train and sealed use disjoint shapes, subject groups, symptom groups and frame pools. Time, place and adverb
words are shared vocabulary and are not part of a family. Sealed stories also share no normalised text with the
v1 train/dev files or the v2 train file, and no 5-word-shingle Jaccard >= 0.8 with any of them.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path

import random

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
ASSESSMENT_TS = REPO / "lib" / "assessment.ts"
ESBUILD_CANDIDATES = [
    REPO / "node_modules" / ".bin" / "esbuild",
    Path.home() / "code" / "Tunza" / "node_modules" / ".bin" / "esbuild",
]
DEFAULT_SEED = 20261018
DEFAULT_OUT = HERE / "data" / "v2"
V1_TRAIN = HERE / "data" / "triage-train.jsonl"
V1_DEV = HERE / "data" / "triage-dev.jsonl"

LANGS = ("en", "sw", "cs")
KINDS = ("go_now", "get_care_today", "monitor_at_home", "need_one_more_answer")
QUOTA = {
    "train": {"go_now": 330, "get_care_today": 240, "monitor_at_home": 250, "need_one_more_answer": 180},
    "sealed": {"go_now": 50, "get_care_today": 34, "monitor_at_home": 34, "need_one_more_answer": 32},
}
BLANK_CAP = {"train": 30, "sealed": 4}  # per language
NEAR_DUP = 0.8

# ---------------------------------------------------------------------------
# Pools. Items never contain "|". gid letters: a,b = train; c,d = sealed.
# ---------------------------------------------------------------------------


def L(s: str) -> list[str]:
    return s.split("|")


# (gid, split, items)
SUBJ = {
    "en": [
        ("en.subj.kin", "train", L("my child|my son|my daughter|my little boy|my little girl|our baby")),
        ("en.subj.elder", "train", L("my mother|my father|my grandmother|my grandfather|my aunt|my uncle")),
        ("en.subj.pron", "train", L("she|he|this one|the patient")),
        ("en.subj.generic", "train", L("the baby|the old man|the old woman|the boy|the girl|the young woman")),
        ("en.subj.neighbour", "sealed", L("my neighbour's child|our neighbour|the young man next door|a woman at the bus stop|a man outside the shop|the cook")),
        ("en.subj.partner", "sealed", L("my husband|my wife|my brother|my sister|my cousin|my nephew")),
        ("en.subj.small", "sealed", L("the toddler|our youngest|the schoolboy|the schoolgirl|the newborn|my friend's baby")),
    ],
    "sw": [
        ("sw.subj.kin", "train", L("mtoto wangu|mwanangu|mtoto wetu|mwanangu wa kike|mwanangu wa kiume|mtoto mdogo")),
        ("sw.subj.elder", "train", L("mama yangu|baba yangu|bibi yangu|babu yangu|shangazi yangu|mjomba wangu")),
        ("sw.subj.pron", "train", L("yeye|huyu|huyo mtoto|mgonjwa|yule mzee|yule mama")),
        ("sw.subj.neighbour", "sealed", L("jirani yangu|jirani yetu|mtoto wa jirani|kijana wa jirani|mwanamke mmoja|mwanamume mmoja")),
        ("sw.subj.partner", "sealed", L("mume wangu|mke wangu|kaka yangu|dada yangu|binamu yangu|mpwa wangu")),
        ("sw.subj.small", "sealed", L("mtoto mchanga|mwanafunzi|mwanafunzi wetu|mdogo wangu|mjukuu wangu|mzee wa mtaa")),
    ],
}

# SYM[lang][topic] = [(gid, split, items)]
SYM: dict[str, dict[str, list]] = {"en": {}, "sw": {}, "cs": {}}


def sym(lang: str, topic: str, letter: str, split: str, items: str) -> None:
    SYM[lang].setdefault(topic, []).append((f"{lang}.{topic}.{letter}", split, L(items)))


# ---- English danger
sym("en", "nw", "a", "train", "won't wake up|is not waking up|is not waking even when shaken|won't wake when called|is not waking when we call|went limp and is not waking")
sym("en", "nw", "b", "train", "cannot be woken and is not waking|will not open the eyes and is not waking|is lying still and not waking|cannot be woken, not waking at all|is not waking and feels hot|has been not waking since the fall")
sym("en", "nw", "c", "sealed", "is unconscious|has become unconscious|went unconscious|is unconscious on the floor|is unconscious and limp|fell unconscious")
sym("en", "nw", "d", "sealed", "won't wake no matter what we try|just won't wake|still won't wake|won't wake after the nap|won't wake and feels cold|wont wake, we tried water")
sym("en", "sz", "a", "train", "is having a seizure|had a seizure just now|keeps having seizures|has had a seizure|started a seizure|had a seizure and is shaking")
sym("en", "sz", "b", "train", "is having convulsions|has convulsions|started convulsions|has convulsions and shaking|had convulsions twice|got convulsions")
sym("en", "sz", "c", "sealed", "is fitting|keeps fitting|is fitting and foaming at the mouth|started fitting|was fitting on the floor|is fitting again")
sym("en", "sz", "d", "sealed", "is shaking all over with a seizure|collapsed with a seizure|went stiff in a seizure|had a convulsion twice|has arms and legs jerking in a seizure|is in a seizure that has lasted minutes")
sym("en", "nb", "a", "train", "has stopped breathing|stopped breathing for a while|stopped breathing then started again|stopped breathing a moment ago|stopped breathing briefly|has stopped breathing completely")
sym("en", "nb", "b", "train", "is not breathing|is not breathing properly|is not breathing at all|is not breathing and looks grey|is not breathing and is pale|is not breathing right")
sym("en", "nb", "c", "sealed", "just stopped breathing|stopped breathing in the car|stopped breathing in sleep|stopped breathing for several seconds|suddenly stopped breathing|stopped breathing while feeding")
sym("en", "nb", "d", "sealed", "was not breathing when I came in|is not breathing and cold|is not breathing, the chest is still|still is not breathing|is not breathing after choking|is not breathing and will not respond")
sym("en", "bl", "a", "train", "has blue lips|has blue lips and cold hands|got blue lips|has blue lips and is weak|now has blue lips|has blue lips after running")
sym("en", "bl", "b", "train", "has a blue face|has a blue face while sleeping|got a blue face|has a blue face and is limp|has a blue face after coughing|came in with a blue face")
sym("en", "bl", "c", "sealed", "is showing blue lips|shows blue lips when crying|woke with blue lips|looks weak with blue lips|came back with blue lips|has gone quiet with blue lips")
sym("en", "bl", "d", "sealed", "now has a blue face|shows a blue face when coughing|looks sick with a blue face|has a blue face after the fit|has a blue face and cold skin|woke up with a blue face")
sym("en", "bd", "a", "train", "is bleeding a lot|is bleeding heavily|keeps bleeding heavily|has heavy bleeding|has heavy bleeding from the leg|is bleeding a lot from the arm")
sym("en", "bd", "b", "train", "has a cut and the bleeding won't stop|has a wound and the bleeding won't stop|has a nosebleed and the bleeding won't stop|has a cut where the bleeding won't stop|has a gash and the bleeding won't stop|has a head wound and the bleeding wont stop")
sym("en", "bd", "c", "sealed", "is bleeding a lot from the head|is bleeding a lot after the accident|started bleeding heavily|was bleeding heavily on the road|is bleeding a lot from the nose|began bleeding a lot")
sym("en", "bd", "d", "sealed", "has heavy bleeding that soaked the cloth|has heavy bleeding since the accident|has heavy bleeding from the foot|has heavy bleeding and feels faint|now has heavy bleeding|keeps bleeding heavily through the bandage")
# injury plus a heavy word: decide() calls it go_now only when mainProblem == injury
sym("en", "inj", "a", "train", "has a deep cut with a lot of blood|has a deep wound that won't stop|has a cut and heavy blood flow|was cut deeply and the blood is heavy|has a wound with a lot of blood|has an injury with heavy blood loss")
sym("en", "inj", "c", "sealed", "cut the arm on tin, a lot of blood|has a wound on the head, a lot of blood|has an injury to the leg, heavy blood|hurt in a fall, a lot of blood|has a deep cut, it won't stop|has a bad wound and heavy blood on the cloth")

# ---- English benign
sym("en", "fev", "a", "train", "has a fever|has had a fever|has fever and chills|is burning up with fever|has a fever and sweats|has a fever that comes and goes")
sym("en", "fev", "c", "sealed", "has a hot body|has a high temperature|has a temperature and shivers|is hot to touch with a temperature|has a hot body and chills|is running a fever")
sym("en", "cough", "a", "train", "has a cough|has a dry cough|has a cough at night|is coughing more now|has a bad cough|is coughing and sneezing")
sym("en", "cough", "c", "sealed", "keeps coughing|has a wet cough|coughs through the night|has had a cough all week|has a cough that will not clear|coughs when lying down")
sym("en", "stom", "a", "train", "has diarrhoea|has loose stools|has a stomach ache|has stomach pain|has diarrhoea and cramps|has a sore tummy")
sym("en", "stom", "c", "sealed", "has runny stools|has cramps in the belly|has a sore belly|has been running to the toilet|has gripes in the stomach|has a tummy upset")
sym("en", "vom", "a", "train", "is vomiting|vomited twice|vomits after eating|has been vomiting|vomited this morning|is being sick")
sym("en", "vom", "c", "sealed", "keeps throwing up|threw up after the meal|feels sick and vomits|has been retching|brought up the food|threw up three times")
sym("en", "head", "a", "train", "has a headache|has a mild headache|complains of a headache|has a pounding headache|has had a headache|has a headache and feels dizzy")
sym("en", "head", "c", "sealed", "says the head hurts|has a throbbing head|has a sore head|keeps holding the head|has head pain|has a dull head")
sym("en", "rash", "a", "train", "has a rash|has a small rash on the arm|has itchy skin|has a rash on the back|has a mild rash|has a rash that itches")
sym("en", "rash", "c", "sealed", "has red spots on the skin|has an itchy patch|keeps scratching a rash|has bumps on the legs|has dry flaky skin|has a blotchy rash")
sym("en", "tired", "a", "train", "is very tired|is tired and weak|feels weak|is tired after school|is exhausted|feels tired all day")
sym("en", "tired", "c", "sealed", "has no energy|is worn out|just wants to lie down|is dragging today|has been low on energy|looks washed out")
sym("en", "minor", "a", "train", "has a small cut on the foot|has a bruise on the knee|scratched a finger|twisted the ankle|has a small cut on the hand|bumped the head lightly")
sym("en", "minor", "c", "sealed", "has a graze on the elbow|stubbed a toe|has a scrape on the knee|has a small burn on the hand|has a splinter in the thumb|has a cut finger from the kitchen")
sym("en", "breath", "a", "train", "is breathing fast|is wheezing|is a bit short of breath|is breathing with effort|is breathing harder than usual|has a whistling chest")
sym("en", "breath", "c", "sealed", "is panting|has a tight chest|finds it hard to catch breath|is struggling to breathe|breathes with a rattle|is out of breath walking")
sym("en", "drink", "a", "train", "is drinking very little|refuses to drink water|drinks only a few sips|will not take fluids|is refusing the cup|drinks less than usual")
sym("en", "drink", "c", "sealed", "will hardly take any water|turns away from the cup|only takes small sips|has stopped wanting drinks|spits out the water|barely drinks")
sym("en", "sleepy", "a", "train", "is very sleepy|is sleepy all day|sleeps most of the day|is sleepier than usual|is drowsy and sleepy|keeps dozing off")
sym("en", "sleepy", "c", "sealed", "is drowsy today|is very drowsy|nods off all the time|is slow and sleepy|seems half asleep|is dozy since noon")
sym("en", "mild", "a", "train", "has a runny nose|is sneezing|has a mild sore throat|has an itchy eye|has a blocked nose|has a slight cold")
sym("en", "mild", "c", "sealed", "has a scratchy throat|has watery eyes|has a stuffy nose|has a little cold|sneezes every morning|has a sore ear")
sym("en", "vague", "a", "train", "is not well|is unwell|is feeling bad|does not look right|is sick|is not feeling good")
sym("en", "vague", "c", "sealed", "is off today|seems under the weather|is not themselves|is not doing great|is poorly|is not quite right")

# ---- Kiswahili danger
sym("sw", "nw", "a", "train", "hajitambui|haamki|haamki hata ukimwita|hajitambui kabisa|haamki hata akitikiswa|hajitambui na haamki")
sym("sw", "nw", "b", "train", "ameanguka na hajitambui|amelala na haamki|macho yamefumba, haamki|amepoteza fahamu, hajitambui|amelala fofofo, haamki|ametulia na hajitambui")
sym("sw", "nw", "c", "sealed", "bado hajitambui|hajitambui kabisa hata tukimwita|amelegea na hajitambui|hajitambui tangu alipoanguka|hajitambui na ni baridi|hajitambui, tumeogopa")
sym("sw", "nw", "d", "sealed", "haamki hata kwa maji usoni|mpaka sasa haamki|haamki kabisa, tumeogopa|haamki akiitwa|haamki na ana joto|haamki hata tukimtikisa")
sym("sw", "sz", "a", "train", "anapata degedege|ana degedege|amepata degedege|ana degedege sasa hivi|anaanza kupata degedege|degedege limemshika")
sym("sw", "sz", "b", "train", "ana kifafa|amepata kifafa|anapata kifafa|kifafa kimemshika|ana kifafa kikali|kifafa kimeanza")
sym("sw", "sz", "c", "sealed", "anatetemeka na degedege|ameshikwa na degedege|ameanza kupata degedege|degedege limerudia|ana degedege tena na tena|amepata degedege mara mbili")
sym("sw", "sz", "d", "sealed", "ana kifafa tena|ameshikwa na kifafa|anatoa povu na kifafa|anaanguka kwa kifafa|kifafa kimemrudia|ana kifafa na mwili mgumu")
sym("sw", "nb", "a", "train", "hapumui|hapumui kabisa|hapumui sasa|hapumui hata kidogo|hapumui kwa muda|hapumui na ameloa jasho")
sym("sw", "nb", "b", "train", "hapumui vizuri|hapumui na ni dhaifu|hapumui tangu alipoanguka|hapumui hata tukimwita|hapumui na amelegea|hapumui hata kwa msaada")
sym("sw", "nb", "c", "sealed", "ghafla hapumui|alikuwa hapumui nilipomkuta|hapumui na mwili ni baridi|sasa hapumui kabisa|hapumui akiwa amelala|hapumui na uso umebadilika")
sym("sw", "nb", "d", "sealed", "hapumui usingizini|hapumui kwa sekunde kadhaa|hapumui, kifua kimetulia|hapumui baada ya kusongwa|bado hapumui|hapumui na hajibu")
sym("sw", "bl", "a", "train", "ana midomo ya bluu|midomo ya bluu imeonekana|ana midomo ya bluu na baridi|ana midomo ya bluu na amechoka|midomo ya bluu na macho yamefumba|ana midomo ya bluu tangu asubuhi")
sym("sw", "bl", "b", "train", "ana midomo ya bluu akilala|midomo ya bluu inaonekana|ana midomo ya bluu na ni dhaifu|amepata midomo ya bluu|ana midomo ya bluu baada ya kukohoa|midomo ya bluu na mikono baridi")
sym("sw", "bl", "c", "sealed", "amegeuka kuwa na midomo ya bluu|ana midomo ya bluu akilia|ameamka na midomo ya bluu|midomo ya bluu na hana nguvu|anaonekana mgonjwa na midomo ya bluu|bado ana midomo ya bluu")
sym("sw", "bl", "d", "sealed", "ana midomo ya bluu na hana nguvu|midomo ya bluu tangu alipoanguka|midomo ya bluu na uso baridi|ana midomo ya bluu mara kwa mara|ghafla ana midomo ya bluu|ana midomo ya bluu hata akipumzika")
sym("sw", "bd", "a", "train", "anatoka damu nyingi|anavuja damu nyingi|ana damu nyingi mguuni|jeraha lina damu nyingi|ana damu nyingi sana|damu nyingi inatoka")
sym("sw", "bd", "b", "train", "damu nyingi inatoka mkononi|ametoka damu nyingi kichwani|anatoka damu nyingi puani|damu nyingi imetoka jeraha|ana damu nyingi na amedhoofika|damu nyingi imeloa kitambaa")
sym("sw", "bd", "c", "sealed", "ametokwa na damu nyingi|anavuja damu nyingi puani|damu nyingi imeloa nguo|ametoka damu nyingi barabarani|anavuja damu nyingi kichwani|damu nyingi inatoka na haikomi")
sym("sw", "bd", "d", "sealed", "ana damu nyingi tangu ajali|amejikata na damu nyingi inatoka|ana jeraha na damu nyingi|ana damu nyingi mguuni na analegea|damu nyingi inamtoka|ana damu nyingi baada ya kuanguka")
# ---- Kiswahili benign
sym("sw", "fev", "a", "train", "ana homa|ana homa na kutetemeka|ana homa kali|ana homa na baridi|ana homa inayopanda|ana homa tangu jana")
sym("sw", "fev", "c", "sealed", "ana homa na kichwa kinauma|ana homa ya usiku|ana homa na jasho|ana homa inayokuja na kuondoka|homa imemshika|ana homa kali sana")
sym("sw", "cough", "a", "train", "anakohoa|ana kikohozi|ana kikohozi kikavu|anakohoa usiku|ana kikohozi kibaya|anakohoa na kupiga chafya")
sym("sw", "cough", "c", "sealed", "anakohoa mfululizo|ana kikohozi cha kohozi|kikohozi hakiishi|anakohoa akilala|ana kikohozi cha wiki nzima|anakohoa asubuhi tu")
sym("sw", "stom", "a", "train", "anaharisha|ana tumbo linauma|ana maumivu ya tumbo|anaumwa na tumbo|ana kuharisha na tumbo|tumbo linamsumbua")
sym("sw", "stom", "c", "sealed", "ameharisha mara mbili|ana kuhara|tumbo linamuuma|ana tumbo la kuvimba|anaenda haja mara nyingi|ana mshtuko wa tumbo")
sym("sw", "vom", "a", "train", "anatapika|ametapika mara mbili|anatapika baada ya kula|ametapika asubuhi|amekuwa akitapika|anajaribu kutapika")
sym("sw", "vom", "c", "sealed", "anarudisha chakula|anajisikia kichefuchefu na kutapika|ametapika chakula chote|amekataa chakula na kutapika|anatapika maji|ametapika mara tatu")
sym("sw", "head", "a", "train", "ana maumivu ya kichwa|kichwa kinauma|analalamika kichwa|ana kichwa kidogo|ana maumivu ya kichwa na kizunguzungu|kichwa kinamuuma kidogo")
sym("sw", "head", "c", "sealed", "kichwa kinamgonga|ana kichwa kizito|anasema kichwa kinamuuma|anashika kichwa|kichwa kimechoka|ana kichwa chenye mawimbi")
sym("sw", "rash", "a", "train", "ana upele|ana upele mdogo mkononi|ana ngozi inayowasha|ana upele mgongoni|ana upele kidogo|ngozi inamwasha")
sym("sw", "rash", "c", "sealed", "ana vipele vyekundu|anajikuna upele|ana kipele kinachowasha|ana madoa mwilini|ngozi imekauka|ana vipele miguuni")
sym("sw", "tired", "a", "train", "amechoka sana|ana uchovu|anahisi dhaifu|amechoka baada ya shule|amechoka kabisa|ana uchovu siku nzima")
sym("sw", "tired", "c", "sealed", "hana nguvu|amechoka mno|anataka kulala tu|amepoteza nguvu kidogo|ni mchovu leo|anaonekana amechoka")
sym("sw", "minor", "a", "train", "ana jeraha dogo mguuni|amechubuka goti|amejikwaruza kidole|amegonga mguu|ana jeraha dogo mkononi|ana mchubuko mdogo")
sym("sw", "minor", "c", "sealed", "ana mchubuko kiwiko|amejikwaa kidole|ana mkwaruzo mkononi|ameungua kidogo mkononi|ana mwiba kidoleni|amejigonga kichwa kidogo")
sym("sw", "breath", "a", "train", "anapumua haraka|anapumua kwa shida|ana kikohozi na kupumua kwa shida|anahema kidogo|kupumua kwake kunamsumbua|anapumua kwa tabu")
sym("sw", "breath", "c", "sealed", "anahema|kifua kinambana|anapumua kwa jitihada|anapumua kwa kelele|anakosa pumzi akitembea|kifua kinamfunga")
sym("sw", "drink", "a", "train", "anakunywa maji kidogo|anakataa kunywa|hanywi maji vizuri|anakunywa mafunda machache|hataki maji|anakunywa kidogo kuliko kawaida")
sym("sw", "drink", "c", "sealed", "hanywi chochote kikubwa|amekataa maji|anageuza kichwa akipewa kikombe|anakunywa funda moja tu|anatema maji|hataki kikombe")
sym("sw", "sleepy", "a", "train", "ana usingizi mwingi|analala sana|ana usingizi sana|anasinzia mchana|ana usingizi kuliko kawaida|analala siku nzima")
sym("sw", "sleepy", "c", "sealed", "anasinzia kila wakati|amelegea na usingizi|ana uchovu na usingizi|ana usingizi mzito|anaonekana ana usingizi|analala bila kula")
sym("sw", "mild", "a", "train", "ana kamasi|anapiga chafya|koo linauma kidogo|jicho linawasha|pua imeziba|ana mafua kidogo")
sym("sw", "mild", "c", "sealed", "pua imeziba kidogo|koo linakwaruza|macho yanatoa machozi|ana mafua mepesi|anapiga chafya asubuhi|sikio linamuuma kidogo")
sym("sw", "vague", "a", "train", "si mzima|anajisikia vibaya|hajisikii vizuri|ni mgonjwa|ana shida|hali yake si nzuri")
sym("sw", "vague", "c", "sealed", "hayuko sawa|anaumwa|hali yake si shwari|anaonekana si vizuri|hayupo vizuri leo|ana tatizo")

# ---- Code-switch hybrids (mixed inside one clause)
sym("cs", "nw", "a", "train", "is haamki kabisa|ni unconscious sasa|amekuwa unconscious|is hajitambui|ame-collapse and haamki|won't wake, haamki hata akiitwa|is not waking, hajitambui")
sym("cs", "nw", "c", "sealed", "hajitambui and won't wake|ame-faint, not waking sana|anaonekana unconscious|yuko unconscious|is unconscious na haamki|amelala, not waking kabisa")
sym("cs", "sz", "a", "train", "ana convulsions|ana degedege and shaking|is having kifafa|got a seizure, degedege|ana seizure sasa|kifafa, convulsions started")
sym("cs", "sz", "c", "sealed", "ana fitting|amepata fitting|ana kifafa and keeps fitting|anapata convulsion|ana seizure tena|degedege, is fitting")
sym("cs", "nb", "a", "train", "hapumui, not breathing|is hapumui|amestopped breathing|hapumui and stopped breathing|ni not breathing|is not breathing, hapumui kabisa")
sym("cs", "nb", "c", "sealed", "ame-stop, hapumui|hapumui kabisa, not breathing|ni not breathing sasa|stopped breathing, hapumui|anaonekana hapumui|has stopped breathing na ni baridi")
sym("cs", "bl", "a", "train", "ana blue lips|midomo ya bluu and cold|has midomo ya bluu|uso una blue face|ana blue lips na weak|ana blue face sasa")
sym("cs", "bl", "c", "sealed", "ana blue lips sana|ana blue face na hana nguvu|midomo ya bluu, looks very weak|amepata blue lips|ana blue face baada ya kukohoa|midomo ya bluu na cold hands")
sym("cs", "bd", "a", "train", "ana bleeding heavily|anatoka damu nyingi, bleeding a lot|has damu nyingi|heavy bleeding kwenye mguu|ana bleeding a lot|anavuja damu nyingi and weak")
sym("cs", "bd", "c", "sealed", "ana heavy bleeding|damu nyingi, won't stop|bleeding won't stop kichwani|ana damu nyingi sana|amejikata, bleeding heavily|ana heavy bleeding baada ya ajali")
sym("cs", "inj", "a", "train", "ana deep cut na a lot of blood|ana jeraha that won't stop|ana jeraha na heavy blood loss|ana wound na a lot ya blood")
sym("cs", "inj", "c", "sealed", "ana cut kubwa, a lot of blood|ana injury na heavy blood|ana wound, it won't stop|ana jeraha kubwa, heavy blood")
sym("cs", "fev", "a", "train", "ana fever|has homa|ana hot body|ana fever na chills|ana temperature")
sym("cs", "fev", "c", "sealed", "ana high temperature|ana homa and chills|hot body, ana homa kali|ana fever kali")
sym("cs", "cough", "a", "train", "ana cough|anakohoa and cough inaendelea|ana dry cough|ana cough usiku")
sym("cs", "cough", "c", "sealed", "ana cough kali|kikohozi, keeps coughing|anakohoa constantly|ana wet cough")
sym("cs", "stom", "a", "train", "ana diarrhoea|ana stomach ache|anaharisha and stomach pain|tumbo inauma, cramps")
sym("cs", "stom", "c", "sealed", "ana runny stool|tumbo linauma, cramps kidogo|ana tummy upset|ameharisha, loose stool")
sym("cs", "vom", "a", "train", "anatapika and vomiting|ana vomiting|anatapika twice")
sym("cs", "vom", "c", "sealed", "ana kutapika and nausea|anarudisha food|ametapika mara three")
sym("cs", "head", "a", "train", "ana headache|ana mild headache|kichwa kinauma, headache")
sym("cs", "head", "c", "sealed", "ana throbbing headache|head ni sore|kichwa ya pain")
sym("cs", "rash", "a", "train", "ana rash ndogo|ana upele, itchy|rash inawasha")
sym("cs", "rash", "c", "sealed", "ana red spots mwilini|ana patch inayowasha|ngozi ni dry na flaky")
sym("cs", "tired", "a", "train", "amechoka and weak|ni very tired|ana uchovu, tired sana")
sym("cs", "tired", "c", "sealed", "has no nguvu|ame-tire sana|ni worn out")
sym("cs", "minor", "a", "train", "ana small cut mguuni|ana bruise kwenye goti|amejikwaruza finger")
sym("cs", "minor", "c", "sealed", "ana scrape ya goti|ana small jeraha|amegonga toe")
sym("cs", "breath", "a", "train", "anapumua fast|ana wheezing|breathing ni ngumu")
sym("cs", "breath", "c", "sealed", "ana tight chest, anahema|anapumua kwa shida and panting|ana kikohozi na breathing ngumu")
sym("cs", "drink", "a", "train", "anakunywa little|hanywi water vizuri|refuses kunywa")
sym("cs", "drink", "c", "sealed", "kunywa maji ni kidogo|hataki kunywa|only takes sips ya maji")
sym("cs", "sleepy", "a", "train", "ana sleepy sana|analala sana, drowsy|ana usingizi and sleepy")
sym("cs", "sleepy", "c", "sealed", "ni drowsy leo|ana usingizi sana, dozing|amelegea and sleepy")
sym("cs", "mild", "a", "train", "ana runny nose na kamasi|ana sneezing|koo ni sore")
sym("cs", "mild", "c", "sealed", "pua imeziba, stuffy|ana watery eyes|ana little cold")
sym("cs", "vague", "a", "train", "ni unwell|hajisikii well|is not feeling vizuri")
sym("cs", "vague", "c", "sealed", "hayuko well|is off leo|si well today")

DANGER_TOPICS = ("nw", "sz", "nb", "bl", "bd", "inj")
DANGER_WEIGHTS = {"nw": 24, "sz": 20, "nb": 20, "bl": 14, "bd": 16, "inj": 6}
CARE_TOPICS = ("fev", "breath", "drink", "sleepy", "cough", "vom", "minor", "stom")
MONITOR_TOPICS = ("head", "rash", "tired", "mild", "minor", "cough", "stom", "vom")
NEED_TOPICS = ("vague", "mild", "tired", "head", "rash", "stom")
BENIGN_TOPICS = ("fev", "cough", "stom", "vom", "head", "rash", "tired", "minor", "breath", "drink", "sleepy", "mild", "vague")

# Shared vocabulary (not part of a family).
SLOT = {
    "en": {
        "time": L("this morning|since this morning|last night|since yesterday|for two days|just now|a few minutes ago|this afternoon|tonight|after lunch|since the weekend|for an hour"),
        "place": L("at home|at the market|at school|on the bus|in the field|at church|near the well|at the shop|in the kitchen|outside|at work|on the road"),
        "advm": L("suddenly|badly|again|completely|really"),
        "advp": L("Right now,|All of a sudden,|For the second time today,|As we speak,|Out of nowhere,"),
        "conn_train": L("and|also|then|but"),
        "conn_sealed": L("and now|and meanwhile|plus|and on top of that"),
        "obs_train": L("I see that|Look,|Help,|I found that"),
        "obs_sealed": L("I think|I am scared because|Someone told me|Just now I noticed that"),
        "ctx": L("Please help.|I do not know what to do.|I am worried.|It is getting worse.|We have called for help.|The clinic is far from here."),
    },
    "sw": {
        "time": L("tangu asubuhi|tangu jana usiku|kwa saa moja|kwa siku mbili|dakika kumi zilizopita|leo asubuhi|sasa hivi|jana jioni|tangu juzi|baada ya chakula cha mchana|usiku wa leo|tangu mchana"),
        "place": L("nyumbani|sokoni|shuleni|kwenye basi|shambani|kanisani|karibu na kisima|dukani|jikoni|nje|kazini|barabarani"),
        "advm": L("ghafla|tena|sana|vibaya|kabisa"),
        "advp": L("Sasa hivi,|Ghafla,|Kwa mara ya pili leo,|Haraka,|Bila kutarajia,"),
        "conn_train": L("na|pia|kisha|lakini"),
        "conn_sealed": L("na sasa|huku|wakati huo huo|tena|pamoja na hilo"),
        "obs_train": L("naona|nimegundua|ninaona kwamba|tazama,"),
        "obs_sealed": L("nadhani|sikia,|naogopa kwa sababu|nimeambiwa|msaada,"),
        "ctx": L("Tafadhali nisaidie.|Sijui nifanye nini.|Naogopa.|Hali inazidi kuwa mbaya.|Tumeita msaada.|Nipo mbali na hospitali."),
    },
}
BARE = {
    "en": {"train": L("unwell|tired|rash|cough|headache|sick|not well|weak|a bit off|sore throat|itchy|feeling bad"),
           "sealed": L("poorly|fatigue|skin rash|tummy|aches|not right|low energy|off colour|sniffles|dizzy")},
    "sw": {"train": L("si mzima|amechoka|upele|kikohozi|tumbo|kichwa|mgonjwa|hajisikii vizuri|dhaifu|anawasha|koo|kamasi"),
           "sealed": L("hayuko sawa|uchovu|vipele|tumbo linauma|maumivu|shida|hali mbaya|anaumwa|kizunguzungu|pua")},
    "cs": {"train": L("mgonjwa lakini unclear|tired sana|rash ndogo|cough kidogo|tumbo pain|head kidogo|sick tu|si well|weak sana|kamasi runny"),
           "sealed": L("poorly sana|uchovu kidogo|itchy mwili|maumivu small|hayuko fine|dizzy kidogo|pua stuffy|ngozi rash")},
}
BLANK = {"en": ["", " ", "  "], "sw": ["\t", "\t ", "  \t"], "cs": ["\n", " \n", "\n  "]}

# shape id -> (split, template, needs)
SHAPES = {
    "T1": ("train", "{subj} {sym}"),
    "T2": ("train", "{subj} {sym} {time}"),
    "T3": ("train", "{time}, {subj} {sym}"),
    "T4": ("train", "{subj} {sym} {place}"),
    "T5": ("train", "{subj} {advm} {sym}"),
    "T6": ("train", "{subj} {sym} {conn_train} {sym2}"),
    "T7": ("train", "{place}, {subj} {sym}"),
    "T8": ("train", "{subj} {sym} {place} {time}"),
    "T9": ("train", "{obs_train} {subj} {sym}"),
    "T10": ("train", "{subj} {sym}, {sym2}"),
    "S1": ("sealed", "{subj} - {sym} ({time})"),
    "S2": ("sealed", "{subj} {sym}. {ctx}"),
    "S3": ("sealed", "{advp} {subj} {sym}"),
    "S4": ("sealed", "{subj} {sym} {conn_sealed} {sym2}"),
    "S5": ("sealed", "{place}: {subj} {sym} {time}"),
    "S6": ("sealed", "{obs_sealed} {subj} {sym}"),
    "S7": ("sealed", "{subj} {sym}; {sym2}"),
    "S8": ("sealed", "{ctx} {subj} {sym} {place}"),
    "S9": ("sealed", "{subj}: {sym} {time}, {ctx_lower}"),
}
SHAPE_IDS = {s: [k for k, v in SHAPES.items() if v[0] == s] for s in ("train", "sealed")}

QUESTIONS = {
    "en": {
        "awake": "Is the person awake and responding normally?",
        "breathing": "Is the person breathing normally right now?",
        "drinking": "Can the person drink normally right now?",
    },
    "sw": {
        "awake": "Je, mtu ana fahamu na anaitikia vizuri?",
        "breathing": "Je, mtu anapumua vizuri kwa sasa?",
        "drinking": "Je, mtu anaweza kunywa maji kwa sasa?",
    },
    "cs": {
        "awake": "Is the person awake na anaitikia?",
        "breathing": "Is the person breathing fine kwa sasa?",
        "drinking": "Can the person kunywa normally?",
    },
}

# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def canon(obj) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def norm_ws(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip().lower()


def norm_words(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(text).lower()).strip()


def shingles(text: str, n: int = 5) -> frozenset:
    toks = norm_words(text).split()
    if not toks:
        return frozenset()
    if len(toks) < n:
        return frozenset({" ".join(toks)})
    return frozenset(" ".join(toks[i:i + n]) for i in range(len(toks) - n + 1))


def jaccard(a: frozenset, b: frozenset) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    return inter / len(a | b) if inter else 0.0


def wchoice(rng: random.Random, pairs):
    total = sum(w for _, w in pairs)
    x = rng.random() * total
    for item, w in pairs:
        x -= w
        if x < 0:
            return item
    return pairs[-1][0]


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(ln) for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]


def row_text(row: dict) -> str:
    return json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n"


# ---------------------------------------------------------------------------
# decide() oracle
# ---------------------------------------------------------------------------


def find_esbuild() -> Path:
    for cand in ESBUILD_CANDIDATES:
        if cand.exists():
            return cand
    raise SystemExit("esbuild not found at " + " or ".join(str(c) for c in ESBUILD_CANDIDATES) + "; cannot label cases")


class Decider:
    """Builds a local bundle of decide() from lib/assessment.ts and labels intakes in batches."""

    def __init__(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="tunza-decide-")
        tmp = Path(self._tmp.name)
        entry = tmp / "_decide_entry.ts"
        entry.write_text(
            "import { decide } from " + json.dumps(str(ASSESSMENT_TS)) + ";\n"
            "const chunks: Buffer[] = [];\n"
            "process.stdin.on('data', (c) => chunks.push(c as Buffer));\n"
            "process.stdin.on('end', () => {\n"
            "  const cases = JSON.parse(Buffer.concat(chunks).toString('utf8'));\n"
            "  process.stdout.write(JSON.stringify(cases.map((c: any) => decide(c))));\n"
            "});\n",
            encoding="utf-8",
        )
        self.bundle = tmp / "decide.cjs"
        esbuild = find_esbuild()
        done = subprocess.run(
            [str(esbuild), str(entry), "--bundle", "--platform=node", "--format=cjs",
             f"--outfile={self.bundle}", "--log-level=error"],
            capture_output=True, text=True, timeout=120)
        if done.returncode != 0:
            raise SystemExit(f"esbuild failed: {done.stderr.strip()}")
        self.esbuild_version = subprocess.run([str(esbuild), "--version"], capture_output=True, text=True).stdout.strip()
        self.bundle_sha256 = sha256_bytes(self.bundle.read_bytes())
        self.assessment_sha256 = sha256_bytes(ASSESSMENT_TS.read_bytes())

    def decide(self, intakes: list[dict]) -> list[dict]:
        if not intakes:
            return []
        done = subprocess.run(
            ["node", str(self.bundle)], input=json.dumps(intakes, ensure_ascii=False).encode("utf-8"),
            capture_output=True, timeout=300)
        if done.returncode != 0:
            raise SystemExit(f"decide() call failed: {done.stderr.decode('utf-8', 'replace').strip()}")
        out = json.loads(done.stdout.decode("utf-8"))
        if len(out) != len(intakes):
            raise SystemExit("decide() returned the wrong number of labels")
        return out

    def close(self) -> None:
        self._tmp.cleanup()


# ---------------------------------------------------------------------------
# Answer construction (mirrors the v1 rows)
# ---------------------------------------------------------------------------


def follow_up_question(language: str, intake: dict) -> str:
    for key in ("awake", "breathing", "drinking"):
        if intake.get(key) in (None, "unknown", ""):
            return QUESTIONS[language][key]
    return QUESTIONS[language]["awake"]


def danger_facts(intake: dict, kind: str) -> list[str]:
    """go_now: field pairs that fired (awake, breathing, drinking order), then the story. Else empty."""
    if kind != "go_now":
        return []
    facts: list[str] = []
    awake, breathing = intake.get("awake"), intake.get("breathing")
    if awake == "not_waking":
        facts.append("awake=not_waking")
    if awake == "sleepy" and breathing == "difficult":
        facts += ["awake=sleepy", "breathing=difficult"]
    if breathing == "severe":
        facts.append("breathing=severe")
    if intake.get("drinking") == "no" and intake.get("who") == "child":
        facts.append("drinking=no")
    if str(intake.get("presentation") or "").strip():
        facts.append(intake["presentation"])
    return facts


def make_answer(language: str, intake: dict, kind: str) -> dict:
    return {
        "disposition": kind,
        "danger_facts": danger_facts(intake, kind),
        "follow_up_question": follow_up_question(language, intake) if kind == "need_one_more_answer" else None,
    }


# ---------------------------------------------------------------------------
# Story composition
# ---------------------------------------------------------------------------


def pick_group(rng: random.Random, lang: str, topic: str, split: str):
    groups = [g for g in SYM[lang].get(topic, []) if g[1] == split]
    return rng.choice(groups) if groups else None


def pick_sym(rng: random.Random, lang: str, topic: str, split: str, subj_lang: str):
    """Return (gid, text) for a symptom clause. For cs, the clause is hybrid or in the language opposite the subject."""
    if lang == "cs":
        hybrid = pick_group(rng, "cs", topic, split)
        if hybrid is not None and (rng.random() < 0.35 or pick_group(rng, "en", topic, split) is None):
            return hybrid[0], rng.choice(hybrid[2])
        other = "sw" if subj_lang == "en" else "en"
        g = pick_group(rng, other, topic, split)
        if g is None:
            g = hybrid
        return g[0], rng.choice(g[2])
    g = pick_group(rng, lang, topic, split)
    return g[0], rng.choice(g[2])


def style(rng: random.Random, text: str) -> str:
    r = rng.random()
    if r < 0.06:
        text = text.upper()
    elif r < 0.20:
        text = text.lower()
    else:
        text = text[:1].upper() + text[1:]
    r = rng.random()
    if text.endswith((".", "!", "?")):
        pass
    elif r < 0.40:
        text += "."
    elif r < 0.43:
        text += "!"
    elif r < 0.46:
        text += "..."
    if rng.random() < 0.07:
        text = text.replace("won't", "wont").replace("WON'T", "WONT")
    return text


def compose(rng: random.Random, lang: str, split: str, main_topic: str, other_topic: str,
            main_is_danger: bool) -> tuple[str, dict]:
    """Build one story. main_topic fills the first clause; other_topic fills the second clause when the shape
    has one. For danger stories the danger clause moves to the second slot half of the time."""
    shape_id = rng.choice(SHAPE_IDS[split])
    template = SHAPES[shape_id][1]
    needs = set(re.findall(r"\{(\w+)\}", template))

    def slot_lang() -> str:
        return rng.choice(("en", "sw")) if lang == "cs" else lang

    subj_lang = slot_lang()
    subj_gid, _, subj_items = rng.choice([g for g in SUBJ[subj_lang] if g[1] == split])
    values: dict[str, str] = {"subj": rng.choice(subj_items)}
    first, second = main_topic, other_topic
    if "sym2" in needs and main_is_danger and rng.random() < 0.5:
        first, second = other_topic, main_topic
    fam_sym: list[str] = []
    topics: list[str] = []
    gid, text = pick_sym(rng, lang, first, split, subj_lang)
    values["sym"] = text
    fam_sym.append(gid)
    topics.append(first)
    if "sym2" in needs:
        gid, text = pick_sym(rng, lang, second, split, slot_lang())
        values["sym2"] = text
        fam_sym.append(gid)
        topics.append(second)
    frames: list[str] = []
    for name in ("time", "place", "advm", "advp"):
        if name in needs:
            values[name] = rng.choice(SLOT[slot_lang()][name])
            if name == "advp":
                frames.append("advp")
    for name in ("conn_train", "conn_sealed", "obs_train", "obs_sealed"):
        if name in needs:
            values[name] = rng.choice(SLOT[slot_lang()][name])
            frames.append(name)
    for name in ("ctx", "ctx_lower"):
        if name in needs:
            ctx = rng.choice(SLOT[slot_lang()]["ctx"])
            values[name] = ctx[:1].lower() + ctx[1:] if name == "ctx_lower" else ctx
            frames.append("ctx")
    text = template.format(**values)
    fam = {"shape": shape_id, "subj": subj_gid, "sym": fam_sym, "topics": topics,
           "frames": sorted(set(f"{lang}.{f}" for f in frames))}
    return text, fam


# ---------------------------------------------------------------------------
# Structured profiles
# ---------------------------------------------------------------------------

WHO_W = [("self", 25), ("household_adult", 25), ("child", 30), ("unknown", 15), (None, 5)]
DUR_W = [("today", 45), ("two_days", 15), ("longer", 7), ("unknown", 25), (None, 8)]
MAIN_ANY_W = [("other", 30), ("breathing", 12), ("injury", 15), ("fever", 6), ("stomach", 6), ("unknown", 19), (None, 12)]
MAIN_QUIET_W = [("other", 40), ("stomach", 20), ("unknown", 28), (None, 12)]


def base_profile(rng: random.Random, confident_bias: float) -> dict:
    def pick(good: str, unknown_w: int):
        return wchoice(rng, [(good, int(confident_bias * 100)), ("unknown", unknown_w), (None, 10)])

    return {
        "who": wchoice(rng, WHO_W),
        "awake": pick("alert", 20),
        "breathing": pick("fine", 20),
        "drinking": pick("yes", 20),
        "duration": wchoice(rng, DUR_W),
        "mainProblem": wchoice(rng, MAIN_QUIET_W),
    }


def profile_danger(rng: random.Random, injury: bool) -> dict:
    if rng.random() < 0.12:
        p = {"who": "unknown", "awake": "unknown", "breathing": "unknown", "drinking": "unknown",
             "duration": "unknown", "mainProblem": "unknown"}
    else:
        p = {
            "who": wchoice(rng, WHO_W),
            "awake": wchoice(rng, [("alert", 40), ("sleepy", 12), ("not_waking", 18), ("unknown", 22), (None, 8)]),
            "breathing": wchoice(rng, [("fine", 45), ("difficult", 15), ("severe", 10), ("unknown", 24), (None, 6)]),
            "drinking": wchoice(rng, [("yes", 40), ("little", 10), ("no", 12), ("unknown", 30), (None, 8)]),
            "duration": wchoice(rng, DUR_W),
            "mainProblem": wchoice(rng, MAIN_ANY_W),
        }
    if injury:
        p["mainProblem"] = "injury"
    return p


CARE_TRIGGERS = ("breathing_difficult", "drink_little", "drink_no", "sleepy", "child_fever", "child_main_fever",
                 "injury", "main_breathing", "longer_fever")


def apply_trigger(p: dict, trig: str, rng: random.Random) -> None:
    if trig == "breathing_difficult":
        p["breathing"] = "difficult"
        if p["awake"] == "sleepy":
            p["awake"] = "alert"
    elif trig == "drink_little":
        p["drinking"] = "little"
    elif trig == "drink_no":
        p["drinking"] = "no"
        if p["who"] == "child":
            p["who"] = rng.choice(["self", "household_adult", "unknown"])
    elif trig == "sleepy":
        p["awake"] = "sleepy"
        if p["breathing"] == "difficult":
            p["breathing"] = "fine"
    elif trig == "child_fever":
        p["who"] = "child"
        if p["drinking"] == "no":
            p["drinking"] = "little"
    elif trig == "child_main_fever":
        p["who"] = "child"
        p["mainProblem"] = "fever"
        if p["drinking"] == "no":
            p["drinking"] = "little"
    elif trig == "injury":
        p["mainProblem"] = "injury"
    elif trig == "main_breathing":
        p["mainProblem"] = "breathing"
    elif trig == "longer_fever":
        p["duration"] = "longer"


def profile_care(rng: random.Random, triggers: list[str]) -> dict:
    p = base_profile(rng, 0.65)
    for t in triggers:
        apply_trigger(p, t, rng)
    return p


def profile_monitor(rng: random.Random) -> dict:
    p = base_profile(rng, 0.78)
    p["mainProblem"] = wchoice(rng, [("other", 45), ("stomach", 20), ("unknown", 20), ("fever", 5), (None, 10)])
    if p["mainProblem"] == "fever" and p["who"] == "child":
        p["who"] = "self"
    return p


def profile_need(rng: random.Random, blank: bool) -> dict:
    if blank:
        p = {
            "who": wchoice(rng, WHO_W),
            "awake": wchoice(rng, [("unknown", 45), (None, 30), ("alert", 25)]),
            "breathing": wchoice(rng, [("unknown", 45), (None, 30), ("fine", 25)]),
            "drinking": wchoice(rng, [("unknown", 45), (None, 30), ("yes", 25)]),
            "duration": wchoice(rng, DUR_W),
            "mainProblem": wchoice(rng, [("other", 20), ("unknown", 25), ("stomach", 10), ("fever", 10), (None, 35)]),
        }
        slots = ["awake", "breathing", "drinking"]
        weak = [k for k in slots if p[k] in ("unknown", None)]
        for k in slots:
            if len(weak) >= 2:
                break
            if k not in weak:
                p[k] = "unknown"
                weak.append(k)
        return p
    p = base_profile(rng, 0.30)
    p["mainProblem"] = None
    p["awake"] = wchoice(rng, [("alert", 30), ("unknown", 45), (None, 25)])
    p["breathing"] = wchoice(rng, [("fine", 30), ("unknown", 45), (None, 25)])
    p["drinking"] = wchoice(rng, [("yes", 30), ("unknown", 45), (None, 25)])
    if p["awake"] == "alert" and p["breathing"] == "fine" and p["drinking"] == "yes":
        p["drinking"] = "unknown"
    return p


# ---------------------------------------------------------------------------
# Candidate generation
# ---------------------------------------------------------------------------


CARE_STORY_TOPIC = {"child_fever": "fev", "longer_fever": "fev", "drink_little": "drink", "drink_no": "drink",
                    "breathing_difficult": "breath", "main_breathing": "breath", "sleepy": "sleepy", "injury": "minor"}


def make_candidate(rng: random.Random, lang: str, split: str, intent: str, allow_blank: bool) -> dict:
    blank = False
    if intent == "danger":
        weights = [(t, w) for t, w in DANGER_WEIGHTS.items() if not (lang == "sw" and t == "inj")]
        dt = wchoice(rng, weights)
        text, fam = compose(rng, lang, split, dt, rng.choice(BENIGN_TOPICS), True)
        profile = profile_danger(rng, "inj" in fam["topics"])
    elif intent == "care":
        trigs = [rng.choice(CARE_TRIGGERS)]
        if rng.random() < 0.10:
            trigs.append(rng.choice(CARE_TRIGGERS))
        if "sleepy" in trigs and "breathing_difficult" in trigs:
            trigs = ["sleepy"]
        topic = rng.choice(CARE_TOPICS)
        if trigs[0] in ("child_fever", "longer_fever") or (trigs[0] in CARE_STORY_TOPIC and rng.random() < 0.5):
            topic = CARE_STORY_TOPIC[trigs[0]]
        text, fam = compose(rng, lang, split, topic, rng.choice(BENIGN_TOPICS), False)
        profile = profile_care(rng, trigs)
    elif intent == "monitor":
        text, fam = compose(rng, lang, split, rng.choice(MONITOR_TOPICS), rng.choice(MONITOR_TOPICS), False)
        profile = profile_monitor(rng)
    else:
        blank = allow_blank and rng.random() < 0.14
        profile = profile_need(rng, blank)
        if blank:
            text = rng.choice(BLANK[lang])
            fam = {"shape": "blank", "subj": "-", "sym": [f"blank.{lang}"], "frames": [], "topics": []}
        elif rng.random() < 0.12:
            text = rng.choice(BARE[lang][split])
            fam = {"shape": f"bare.{split}", "subj": "-", "sym": [f"bare.{lang}.{split}"], "frames": [], "topics": []}
        else:
            text, fam = compose(rng, lang, split, rng.choice(NEED_TOPICS), rng.choice(NEED_TOPICS), False)
    if not blank and not fam["shape"].startswith("bare"):
        text = style(rng, text)
    intake = {
        "who": profile["who"], "presentation": text, "awake": profile["awake"], "breathing": profile["breathing"],
        "drinking": profile["drinking"], "duration": profile["duration"], "mainProblem": profile["mainProblem"],
    }
    return {"intake": intake, "lang": lang, "intent": intent, "fam": fam, "blank": blank}


class Refs:
    """Reference stories a split must not collide with."""

    def __init__(self) -> None:
        self.norm: set[str] = set()      # lower + collapsed whitespace
        self.words: set[str] = set()     # alnum words
        self.index: dict[str, list[int]] = {}
        self.sets: list[frozenset] = []

    def add(self, text: str) -> None:
        if not norm_ws(text):
            return
        self.norm.add(norm_ws(text))
        self.words.add(norm_words(text))
        sh = shingles(text)
        i = len(self.sets)
        self.sets.append(sh)
        for s in sh:
            self.index.setdefault(s, []).append(i)

    def collides(self, text: str) -> str | None:
        if norm_ws(text) in self.norm or norm_words(text) in self.words:
            return "shared_text"
        sh = shingles(text)
        seen: set[int] = set()
        for s in sh:
            for i in self.index.get(s, ()):
                if i in seen:
                    continue
                seen.add(i)
                if jaccard(sh, self.sets[i]) >= NEAR_DUP:
                    return "near_duplicate"
        return None


def build_split(split: str, seed: int, decider: Decider, refs: Refs, stats: Counter) -> list[dict]:
    """Generate one split. Returns accepted records (intake, answer, lang, fam)."""
    accepted: list[dict] = []
    quota = QUOTA[split]
    own = Refs()  # within-split dedupe uses the same machinery for exact text only
    seen_rows: set[str] = set()
    for lang in LANGS:
        rng = random.Random(f"tunza-v2|{seed}|{split}|{lang}")
        bins = Counter()
        blanks = 0
        rounds = 0
        while any(bins[k] < quota[k] for k in KINDS):
            rounds += 1
            if rounds > 400:
                raise SystemExit(f"could not fill quotas for {split}/{lang}: {dict(bins)}")
            need = {k: quota[k] - bins[k] for k in KINDS}
            intents = [("danger", need["go_now"]), ("care", need["get_care_today"]),
                       ("monitor", need["monitor_at_home"]), ("need", need["need_one_more_answer"])]
            intents = [(i, w) for i, w in intents if w > 0]
            cands = [make_candidate(rng, lang, split, wchoice(rng, intents), blanks < BLANK_CAP[split])
                     for _ in range(500)]
            labels = decider.decide([c["intake"] for c in cands])
            for c, lab in zip(cands, labels):
                kind = lab.get("kind")
                if kind not in KINDS:
                    raise SystemExit(f"unexpected decide() kind: {kind!r}")
                if c["intent"] == "danger" and kind != "go_now":
                    stats["dropped_danger_story_not_go_now"] += 1
                    continue
                if kind == "go_now" and c["intent"] != "danger":
                    stats["dropped_go_now_without_danger_story"] += 1
                    continue
                if bins[kind] >= quota[kind]:
                    stats["dropped_bin_full"] += 1
                    continue
                text = c["intake"]["presentation"]
                is_blank = not norm_ws(text)
                if is_blank:
                    if blanks >= BLANK_CAP[split]:
                        stats["dropped_blank_cap"] += 1
                        continue
                else:
                    if norm_words(text) in own.words or norm_ws(text) in own.norm:
                        stats["dropped_duplicate_story"] += 1
                        continue
                    why = refs.collides(text)
                    if why:
                        stats["dropped_" + why] += 1
                        continue
                intake = c["intake"]
                key = canon({**intake, "presentation": norm_ws(text)})
                if key in seen_rows:
                    stats["dropped_duplicate_row"] += 1
                    continue
                seen_rows.add(key)
                if is_blank:
                    blanks += 1
                else:
                    own.add(text)
                bins[kind] += 1
                accepted.append({"intake": intake, "answer": make_answer(lang, intake, kind),
                                 "lang": lang, "fam": c["fam"], "intent": c["intent"]})
        stats[f"{split}_{lang}_rounds"] = rounds
    return accepted


def order_rows(split: str, seed: int, rows: list[dict]) -> list[dict]:
    rng = random.Random(f"tunza-v2|{seed}|{split}|order")
    rows = list(rows)
    rng.shuffle(rows)
    return rows


def family_string(lang: str, fam: dict) -> str:
    return "|".join([lang, "shape=" + fam["shape"], "subj=" + fam["subj"], "sym=" + "+".join(fam["sym"]),
                     "frames=" + "+".join(fam["frames"])])


# ---------------------------------------------------------------------------
# Verification (used by main() and by the tests)
# ---------------------------------------------------------------------------


def family_sets(entries: list[dict]) -> dict[str, set]:
    out = {"shape": set(), "subj": set(), "sym": set(), "frames": set()}
    for e in entries:
        if e["shape"] == "blank":
            continue
        out["shape"].add(e["shape"])
        out["subj"].add(e["subj"])
        out["sym"].update(e["sym"])
        out["frames"].update(e["frames"])
    for k in out:
        out[k].discard("-")
    return out


def verify(out_dir: Path) -> dict:
    train = read_jsonl(out_dir / "triage-train.jsonl")
    sealed = read_jsonl(out_dir / "triage-sealed.jsonl")
    fams = json.loads((out_dir / "families.json").read_text(encoding="utf-8"))
    v1 = read_jsonl(V1_TRAIN) + read_jsonl(V1_DEV)
    report: dict = {}
    for name, rows in (("train", train), ("sealed", sealed)):
        texts = [norm_ws(r["intake"]["presentation"]) for r in rows]
        nonblank = [t for t in texts if t]
        assert len(set(nonblank)) == len(nonblank), f"{name}: repeated story text"
        keys = [canon({**r["intake"], "presentation": norm_ws(r["intake"]["presentation"])}) + canon(r["answer"]) for r in rows]
        assert len(set(keys)) == len(keys), f"{name}: duplicate rows"
        assert len(fams[name]) == len(rows)
        for r in rows:
            assert r["answer"]["disposition"] in KINDS
        report[name] = {"rows": len(rows), "distinct_stories": len(set(texts)), "nonblank_distinct": len(set(nonblank))}
    v1_norm = {norm_ws(r["intake"]["presentation"]) for r in v1} - {""}
    for name, rows in (("train", train), ("sealed", sealed)):
        for r in rows:
            t = norm_ws(r["intake"]["presentation"])
            assert t not in v1_norm, f"{name} shares a story with v1 train/dev: {t!r}"
    train_norm = {norm_ws(r["intake"]["presentation"]) for r in train} - {""}
    for r in sealed:
        assert norm_ws(r["intake"]["presentation"]) not in train_norm
    # near duplicates
    refs_v1 = Refs()
    for r in v1:
        refs_v1.add(r["intake"]["presentation"])
    for r in train:
        assert refs_v1.collides(r["intake"]["presentation"]) is None
    refs_all = Refs()
    for r in v1 + train:
        refs_all.add(r["intake"]["presentation"])
    for r in sealed:
        assert refs_all.collides(r["intake"]["presentation"]) is None
    ft, fs = family_sets(fams["train"]), family_sets(fams["sealed"])
    for k in ft:
        assert not (ft[k] & fs[k]), f"family leak in {k}: {sorted(ft[k] & fs[k])}"
    train_fam = {e["family"] for e in fams["train"] if e["shape"] != "blank"}
    assert not (train_fam & {e["family"] for e in fams["sealed"] if e["shape"] != "blank"})
    report["family_overlap"] = {k: len(ft[k] & fs[k]) for k in ft}
    return report


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def count_table(rows: list[dict], fams: list[dict]) -> dict:
    table: dict = {}
    for r, f in zip(rows, fams):
        table.setdefault(f["lang"], Counter())[r["answer"]["disposition"]] += 1
    return {lang: dict(table[lang]) for lang in LANGS}


def generate(seed: int, out_dir: Path) -> dict:
    decider = Decider()
    try:
        stats: Counter = Counter()
        v1_rows = read_jsonl(V1_TRAIN) + read_jsonl(V1_DEV)
        refs = Refs()
        for r in v1_rows:
            refs.add(r["intake"]["presentation"])
        train_recs = order_rows("train", seed, build_split("train", seed, decider, refs, stats))
        for r in train_recs:
            refs.add(r["intake"]["presentation"])
        sealed_recs = order_rows("sealed", seed, build_split("sealed", seed, decider, refs, stats))
        out_dir.mkdir(parents=True, exist_ok=True)
        manifest_files: dict = {}
        fam_out: dict = {}
        for name, recs in (("train", train_recs), ("sealed", sealed_recs)):
            rows = [{"intake": r["intake"], "answer": r["answer"]} for r in recs]
            text = "".join(row_text(r) for r in rows)
            path = out_dir / f"triage-{name}.jsonl"
            path.write_text(text, encoding="utf-8")
            fam_out[name] = [
                {"line": i, "lang": r["lang"], "family": family_string(r["lang"], r["fam"]),
                 "shape": r["fam"]["shape"], "subj": r["fam"]["subj"], "sym": r["fam"]["sym"],
                 "frames": r["fam"]["frames"], "topics": r["fam"].get("topics", []), "intent": r["intent"]}
                for i, r in enumerate(recs)]
            texts = [norm_ws(r["intake"]["presentation"]) for r in rows]
            manifest_files[f"triage-{name}.jsonl"] = {
                "rows": len(rows),
                "sha256": sha256_bytes(text.encode("utf-8")),
                "distinct_stories_nonblank": len({t for t in texts if t}),
                "distinct_normalised_presentations_including_blank": len(set(texts)),
                "blank_story_rows": sum(1 for t in texts if not t),
                "by_language_and_disposition": count_table(rows, fam_out[name]),
                "by_disposition": dict(Counter(r["answer"]["disposition"] for r in rows)),
                "by_language": dict(Counter(f["lang"] for f in fam_out[name])),
            }
        (out_dir / "families.json").write_text(json.dumps(fam_out, indent=1, sort_keys=True, ensure_ascii=False) + "\n",
                                               encoding="utf-8")
        report = verify(out_dir)
        manifest = {
            "schema_version": 2,
            "generator": "tools/tunza-train/gen_cases.py",
            "generator_sha256": sha256_bytes(Path(__file__).read_bytes()),
            "command": f"python3 tools/tunza-train/gen_cases.py --seed {seed} --out tools/tunza-train/data/v2",
            "seed": seed,
            "jev_derived": False,
            "clinical_data": False,
            "model_written_text": False,
            "label_source": "decide() in lib/assessment.ts",
            "assessment_ts_sha256": decider.assessment_sha256,
            "decide_bundle_sha256": decider.bundle_sha256,
            "esbuild_version": decider.esbuild_version,
            "dev_file_checked_against": {"path": "data/triage-dev.jsonl", "sha256": sha256_bytes(V1_DEV.read_bytes())},
            "v1_train_checked_against": {"path": "data/triage-train.jsonl", "sha256": sha256_bytes(V1_TRAIN.read_bytes())},
            "files": manifest_files,
            "families_sidecar": {"path": "families.json", "sha256": sha256_bytes((out_dir / "families.json").read_bytes())},
            "leakage_checks": {
                "family_overlap_train_vs_sealed": report["family_overlap"],
                "shingle_size": 5, "jaccard_threshold": NEAR_DUP,
                "blank_stories": "exempt from shared-text checks (no text to leak); capped per language",
            },
            "generation_drops": {k: v for k, v in sorted(stats.items()) if k.startswith("dropped")},
            "quotas_per_language": QUOTA,
            "dispositions_absent": ["escalate", "abstain"],
        }
        (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return manifest
    finally:
        decider.close()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--seed", type=int, default=DEFAULT_SEED)
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    a = ap.parse_args()
    manifest = generate(a.seed, Path(a.out))
    print(json.dumps({k: {"rows": v["rows"], "by_disposition": v["by_disposition"], "by_language": v["by_language"],
                          "distinct_stories_nonblank": v["distinct_stories_nonblank"], "sha256": v["sha256"]}
                      for k, v in manifest["files"].items()}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
