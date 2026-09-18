"""Six-way requirement classification: a deterministic multilingual lexicon.

This is a triage pass, not the final classifier. It resolves roughly two thirds
of requirement occurrences cheaply and deterministically; whatever it cannot
place is routed to the LLM stage, which keeps that stage's cost proportionate.

Two properties matter and are easy to get wrong:

1. Patterns anchor on a *leading* word boundary only, so stems match their
   inflections across languages (``communicat`` covers communication,
   communicative, communicatie). Requiring a trailing boundary silently breaks
   every stem rule.
2. Rules run against text already passed through ``atomise.normalise``, where
   accents are stripped and apostrophes have become spaces. Patterns must be
   written against that form: ``esprit d equipe``, not ``esprit d'équipe``.

Rules are ordered most-specific first and the first match wins, so "fluency in
English" resolves as *language* rather than *soft*, and a named tool resolves as
*technical* before the generic "experience with…" fallback can apply.
"""

from __future__ import annotations

import re

LANG_NAMES = re.compile(
    r"\b(english|anglais|englisch|inglese|ingl[eé]s|engels|"
    r"fran[cç]ais|french|franz[oö]sisch|francese|franc[eé]s|frans|"
    r"german|deutsch|allemand|tedesco|alem[aá]n|duits|"
    r"dutch|n[eé]erlandais|niederl[aä]ndisch|olandese|nederlands|"
    r"italian|italien|italienisch|italiano|italiaans|"
    r"spanish|espagnol|spanisch|spagnolo|espa[nñ]ol|spaans|"
    r"portuguese|portugais|portugiesisch|portoghese|portugu[eé]s|"
    r"polish|polnisch|polacco|polski|swedish|schwedisch|svenska|"
    r"danish|d[aä]nisch|dansk|norwegian|norsk|finnish|suomi|czech|"
    r"romanian|rom[aâ]n|hungarian|magyar|greek|turkish|arabic|"
    r"chinese|mandarin|russian|russisch|ukrainian)",
    re.I,
)

# Each rule is (type, *patterns). All patterns must match for the rule to fire.
RULES: list[tuple] = [
    # 1. language proficiency — a language name plus a proficiency marker
    (
        "language",
        re.compile(
            r"\b(fluen|fluid|mother ?tongue|native speaker|madrelingua|langue maternelle|"
            r"muttersprache|proficiency in|command of|niveau [abc][12]|level [abc][12]|"
            r"[abc][12] level|business level|conversational|verhandlungssicher|kenntnis|"
            r"conoscenza della lingua|ma[iî]trise|padronanza|goede beheersing|kennis van het|"
            r"good written|good spoken|very good)",
            re.I,
        ),
        LANG_NAMES,
    ),
    (
        "language",
        LANG_NAMES,
        re.compile(
            r"\b(spoken|written|oral|scritto|parlato|[ée]crit|parl[ée]|gesprochen|"
            r"geschrieben|mondeling|schriftelijk|c1|c2|b1|b2|a2)\b",
            re.I,
        ),
    ),
    # German and Dutch compounds bind the marker to the language name
    # (englischkenntnisse), so no word boundary precedes it.
    (
        "language",
        re.compile(
            r"(kenntnis|sprachniveau|sprachlich|talenkennis|sehr gut|gute|goede|"
            r"buona conoscenza|bon niveau)",
            re.I,
        ),
        LANG_NAMES,
    ),
    # 2. formal credentials
    (
        "credential",
        re.compile(
            r"\b(bachelor|master'?s|mba\b|phd|ph\.d|doctorate|degree|diploma|dipl[oô]m|"
            r"laurea|licence|licenciatura|abschluss|studium|hochschul|universit|"
            r"bac ?\+ ?\d|hbo\b|graduat|bsc\b|msc\b|beng\b|meng\b|apprenticeship|"
            r"ausbildung|lehre\b|titolo di studio|certification|certified|certificat|"
            r"zertifi|certificaz|iso ?\d|pmp\b|prince2|scrum master|cissp|cfa\b|acca|"
            r"cpa\b|itil|togaf|six sigma|security clearance|habilitation)",
            re.I,
        ),
    ),
    (
        "credential",
        re.compile(
            r"\b(driv\w* licen[cs]e|driver'?s licen[cs]e|permis [ab]\b|f[uü]hrerschein|"
            r"patente [ab]\b|rijbewijs|carnet de conducir|carta de condu[cç][aã]o|k[oö]rkort)",
            re.I,
        ),
    ),
    # 3. availability and working conditions
    (
        "availability",
        re.compile(
            r"\b(willing\w* to travel|available to travel|travel .{0,15}(required|frequently|%)|"
            r"disponibilit|d[ée]placement|reisebereitschaft|bereit zu reisen|bereidheid|"
            r"beschikbaarheid|relocat|umzug|shift work|shifts?\b|schichtarbeit|travail post[ée]|"
            r"turni\b|weekend|week-end|samedi|saturday|sunday|sonntag|domenica|s[aá]bado|"
            r"on ?call|standby|bereitschaft|night work|nachtarbeit|lavoro notturno|"
            r"full[- ]time|part[- ]time|vollzeit|teilzeit|temps plein|temps partiel|tempo pieno|"
            r"flexible hours|horaires flexibles|overtime|straordinari|mobilit|onsite presence|"
            r"be based in|resident in|domicili)",
            re.I,
        ),
    ),
    # 4. domain and regulatory knowledge
    (
        "domain",
        re.compile(
            r"\b(industry (knowledge|experience|background)|sector (knowledge|experience)|"
            r"domain (knowledge|expertise)|market knowledge|"
            r"knowledge of the .{0,25}(market|sector|industry)|"
            r"conoscenza del (settore|mercato)|connaissance du (secteur|march[ée])|"
            r"branchenkenntnis|marktkenntnis|kennis van de (markt|sector)|"
            r"conocimiento del (sector|mercado)|regulat|compliance|gdpr|rgpd|dsgvo|mifid|"
            r"basel|solvency|hipaa|fda\b|gmp\b|gxp\b|ifrs|us ?gaap|hgb\b|sox\b|kyc\b|aml\b|"
            r"anti[- ]money|pharmacovigilance|clinical trial|medical device|aspice|iatf|atex|"
            r"reach\b|ce marking|banking|insurance|retail sector|public sector|semiconduct|"
            r"aerospace|defen[cs]e)",
            re.I,
        ),
    ),
    # 5. named technologies, tools and platforms
    (
        "technical",
        re.compile(
            r"\b(sql|python|java\b|javascript|typescript|c\+\+|c#|\.net|golang|\bgo\b|rust\b|"
            r"scala\b|kotlin|swift\b|php\b|ruby|perl\b|matlab|\br\b|sas\b|spss|stata|react|"
            r"angular|vue\b|node\.?js|django|flask|spring\b|laravel|symfony|rails|aws\b|azure|"
            r"gcp\b|google cloud|kubernetes|docker|terraform|ansible|jenkins|gitlab|github|"
            r"\bgit\b|ci/?cd|devops|linux|unix|windows server|bash\b|powershell|sap\b|abap|"
            r"salesforce|hubspot|dynamics|oracle|postgres|mysql|mongodb|redis|elasticsearch|"
            r"kafka|spark\b|hadoop|airflow|dbt\b|snowflake|databricks|bigquery|redshift|"
            r"tableau|power ?bi\b|qlik|looker|excel\b|vba\b|machine learning|deep learning|"
            r"nlp\b|llm\b|tensorflow|pytorch|scikit|pandas|numpy|api\b|rest\b|graphql|"
            r"microservice|etl\b|elt\b|data (pipeline|warehouse|model|engineering)|cad\b|"
            r"autocad|solidworks|catia|plc\b|scada|simulink|figma|photoshop|jira|confluence|"
            r"agile|scrum|kanban|safe\b|erp\b|crm\b|cybersecurity|penetration test|firewall|"
            r"tcp/?ip|helm\b|grafana|prometheus)",
            re.I,
        ),
    ),
    # 6. soft skills — must precede the generic technical fallback
    (
        "soft",
        re.compile(
            r"\b(communicat|kommunikation|comunicaz|comunicac|team ?(player|work|spirit)|"
            r"teamf[aä]hig|teamgeist|esprit d ?[ée]quipe|capacit\w* [aà] travailler|"
            r"travailler en [ée]quipe|lavoro di squadra|spirito di squadra|samenwerk|"
            r"trabajo en equipo|interpersonal|relationship|stakeholder management|leadership|"
            r"autonom|self[- ]?(starter|motivated|driven|sufficient)|proactiv|proattiv|"
            r"initiative|eigeninitiative|problem[- ]?solving|probleml[oö]s|analytic|analytisch|"
            r"analitic|attention to detail|detail[- ]oriented|rigueur|rigoros|rigor|precisione|"
            r"nauwkeurig|organi[sz]ation|organisatie|organizzaz|organisatorisch|time management|"
            r"gestion du temps|priorit|flexib|adaptab|resilien|stress|curios|creativ|kreativ|"
            r"negotiat|verhandlung|n[ée]gociation|trattativ|persuas|"
            r"customer[- ]?(oriented|focus)|service[- ]oriented|kundenorientier|sens du service|"
            r"empath|listening|[ée]coute|ascolto|presentation skills|public speaking|"
            r"written and verbal|hands[- ]on|can[- ]do|entrepreneur|ownership|accountab|"
            r"pragmat|result[s]?[- ](oriented|driven)|zielorientier|orientado a resultados|"
            r"strukturier|structur|selbstst?[aä]ndig|zelfstandig|f[aä]higkeit|arbeitsweise|"
            r"ability to work|able to work|capacity to work|dynami|motivat|passion|enthusias|"
            r"reliab|zuverl[aä]ssig|affidabil|sociab|outgoing|assertiv|drive\b)",
            re.I,
        ),
    ),
    # 7. technical work described without naming a tool
    (
        "technical",
        re.compile(
            r"\b(programming|coding|development|software|algorithm|architecture|database|"
            r"scripting|automation|infrastructure|cloud|frontend|front[- ]end|backend|"
            r"back[- ]end|full[- ]stack|data (analysis|science)|statistic|modelling|modeling|"
            r"testing|debugging|version control|programmier|entwicklung|datenbank|"
            r"programmazione|sviluppo|programmation|d[ée]veloppement|ontwikkeling|technical|"
            r"technisch|tecnic|t[ée]chnic)",
            re.I,
        ),
    ),
    # 8. a named field, discipline or industry — domain by what the object IS.
    #
    # Placed after the tool and activity rules on purpose. The type of a
    # requirement is decided by what is being asked about, not by how the ask is
    # phrased, so a named product beats a field name: `Salesforce Marketing
    # Cloud` is technical even though it contains `marketing`, and `marketing
    # automation` is a technical activity, while `knowledge in marketing` is
    # domain. Running this rule earlier would swallow all three.
    (
        "domain",
        re.compile(
            r"\b(marketing|advertis|publicit|werbung|logistic|logistik|logistiq|logistica|"
            r"supply chain|lieferkette|approvisionnement|procurement|einkauf|achats|"
            r"automotive|automobil|automobile|aerospace|a[ée]ronautique|luftfahrt|"
            r"pharma|biotech|life science|medizintechnik|healthcare|gesundheitswesen|"
            r"sant[ée]|sanit[aà]|legal|juridi|recht|jurid|tax\b|steuer|fiscal|audit|"
            r"accounting|comptabilit|buchhaltung|contabil|treasury|payroll|lohnbuchhaltung|"
            r"human resources|\bhr\b|personalwesen|ressources humaines|recruitment|"
            r"recrutement|personalbeschaffung|e[- ]?commerce|manufactur|fertigung|"
            r"produktion|construction|bauwesen|b[aâ]timent|edilizia|telecom|"
            r"real estate|immobilien|immobili|hospitality|hotellerie|tourism|tourisme|"
            r"consulting|beratungsbranche|conseil|media\b|publishing|verlagswesen|"
            r"education|bildungswesen|[ée]ducation|agricultur|agrar|agricol|"
            r"food industry|lebensmittel|agroaliment|fashion|mode\b|luxury|luxus|luxe\b|"
            r"gaming|igaming|fintech|insurtech|proptech|mobility|mobilit[aä]t|"
            r"transport|logistiek|maritime|shipping|schifffahrt|rail\b|bahn\b|aviation|"
            r"chemical|chemie|chimi|mining|bergbau|utilit|energiewirtschaft|"
            r"renewable|erneuerbare|[ée]nergies renouvelables|textile|packaging|verpackung|"
            r"fmcg|cpg\b|wholesale|grosshandel|grossiste|"
            r"capital market|investment banking|asset management|private equity|"
            r"venture capital|wealth management|payment|zahlungsverkehr|lending|"
            r"credit risk|underwriting|claims handling|actuarial|aktuariat|"
            # Commercial practice. Karimi's call, 2026-09-03: knowing how selling
            # works in a market is knowledge of a practice area, so it belongs
            # here positively rather than by elimination. Placed after the soft
            # rule on purpose — `negotiation skills` is a disposition and stays
            # soft, while `knowledge of sales cycles` is domain.
            r"account management|key account|sales cycle|sales process|"
            r"sales pipeline|pipeline management|territory management|"
            r"prospect(?:ing|ion|ie)|akquise|neukundengewinnung|"
            r"business development|d[ée]veloppement commercial|"
            r"lead generation|leadgenerierung|generazione di lead|"
            r"sales technique|techniques? de vente|verkaufstechnik|"
            r"tecniche di vendita|t[ée]cnicas de venta|habilidades de venta|"
            r"sales target|revenue target|quota attainment|sales quota|"
            r"upsell|cross[- ]?sell|customer success|account growth|"
            r"merchandising|category management|retail operations|"
            r"b2b|b2c|inside sales|field sales|channel sales|"
            r"experi[eê]ncia comercial|exp[ée]rience commerciale|"
            r"esperienza commerciale|experiencia comercial)",
            re.I,
        ),
    ),
]

# Rule 9 used to assign `technical` to any phrase framed as `experience with`,
# `knowledge of`, `kenntnisse in` and so on, with no signal about the object at
# all. It was removed on 2026-09-03 because it classified by grammar rather than
# by content: `knowledge in marketing` came out technical, and so did every
# other description-shaped requirement, which is what reduced domain knowledge
# to 1 correct label in 31 on the validated sample.
#
# Nothing replaces it. A phrase whose object this lexicon cannot recognise now
# returns None, and `classify_embed` routes it to the embedding classifier —
# which does not need the object to be nameable. Abstaining is strictly better
# than a confident wrong answer here, because an abstention is recoverable
# downstream and a misclaim is not.


def classify(phrase: str) -> str | None:
    """Return the requirement type, or None if no rule fires.

    `phrase` must already be normalised — see the module docstring.
    """
    for rule_type, *patterns in RULES:
        if all(p.search(phrase) for p in patterns):
            return rule_type
    return None
