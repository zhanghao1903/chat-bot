from __future__ import annotations

import re
import unicodedata

# These rules are application-owned and intentionally conservative. Recognition model output
# is untrusted: a proposal is rejected when it names a prohibited attribute or uses a relation
# that could encode one without naming the category.
_PROHIBITED_ATTRIBUTE_PATTERNS = (
    re.compile(
        r"\b(?:politic(?:al|s)?|party affiliation|democratic party|republican party|"
        r"communist party|labou?r party|conservative party|liberal party|green party|"
        r"gop|ccp|cpc|communis[mt]|socialis[mt]|fascis[mt])\b|"
        r"政治|政党|党派|民主党|共和党|共产党|国民党|工党|保守党|自民党|民进党|"
        r"共产主义|社会主义|法西斯",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:religio(?:n|us)|christian(?:ity)?|catholic|protestant|muslim|islam(?:ic)?|"
        r"jewish|judaism|buddhis[mt]|hindu(?:ism)?|sikh(?:ism)?|mormon|atheis[mt]|"
        r"jain(?:ism)?|tao(?:ism|ist)?|shinto|bah[aá]['’]?i|church|mosque|synagogue|"
        r"worship|bapti[sz]ed|ramadan)\b|"
        r"宗教|基督徒?|天主教|新教|伊斯兰教|穆斯林|犹太教|佛教徒?|印度教|锡克教|"
        r"摩门教|无神论|教堂|清真寺|犹太会堂|礼拜|祈祷|受洗",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:sexual orientation|homosexual|heterosexual|bisexual|lesbian|gay|"
        r"lgbtq?\+?|queer|came out)\b|性取向|同性恋|异性恋|双性恋|女同性恋|男同性恋|"
        r"酷儿|出柜",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:disease|medical condition|medical history|diagnos(?:is|ed)|prescription|"
        r"medication|diabet(?:es|ic)|cancer|depression|anxiety disorder|bipolar|adhd|"
        r"autis[mt]|hiv|aids|epilepsy|asthma|schizophrenia|ptsd|ocd|crohn['’]?s?|"
        r"arthritis|hypertension|humira|metformin|insulin|prozac|sertraline)\b|"
        r"疾病|病史|病历|确诊|处方|服药|药物|糖尿病|癌症|抑郁症|焦虑症|双相|"
        r"注意力缺陷|自闭症|艾滋|癫痫|哮喘|精神分裂|创伤后|强迫症|克罗恩|"
        r"关节炎|高血压|二甲双胍|胰岛素",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:exact address|home address|street address|postal code|zip code|"
        r"(?:lives?|resides?) at \d+)\b|精确地址|家庭住址|家住|住址|门牌号|邮政编码|"
        r"邮编|住在.{0,20}(?:路|街|号|栋|单元|室)",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:financial condition|income|salary|net worth|account balance|debt|owes?|"
        r"loan|mortgage|bankrupt(?:cy)?|credit(?:worthy| score)?|defaulted?|co-?signer)\b|"
        r"财务状况|收入|月薪|年薪|资产|账户余额|欠债|负债|贷款|房贷|破产|信用|"
        r"违约|担保人",
        re.IGNORECASE,
    ),
)
_UNCERTAIN_SENSITIVE_RELATION = re.compile(
    r"\b(?:supports?|backs?|votes? for|campaigns? for|affiliated with|member of|"
    r"converted to|attends?.{0,16}\b(?:mass|services?)|prays?|takes? [a-z][\w-]* "
    r"(?:daily|every|for treatment)|prescribed|treated for|suffers? from|living with|"
    r"came out as|attracted to|resides? at|lives? at|earns?|makes? \$|owes?)\b|"
    r"支持|拥护|投票给|隶属于|加入.{0,12}党|信奉|皈依|每周.{0,8}礼拜|做礼拜|"
    r"服用|被诊断|确诊为|住在|家住|月入|年收入|欠了",
    re.IGNORECASE,
)
_HIGH_IMPACT_DECISION = re.compile(
    r"\b(?:risk score|risk rating|credit risk|creditworthy|hiring candidate|"
    r"employment suitability|should (?:not )?be hired|loan eligibility|"
    r"insurance risk|housing eligibility|education admission|criminal risk)\b|"
    r"(?:高影响|信用|就业|招聘|贷款|保险|住房|入学|犯罪).{0,12}(?:评分|评级|"
    r"风险|适合|资格)|(?:应该|不应).{0,8}(?:录用|放贷|承保|录取)",
    re.IGNORECASE,
)


def memory_safety_rejection(statement: str) -> str | None:
    """Return a stable rejection code for prohibited or uncertain member inferences."""

    normalized = unicodedata.normalize("NFKC", statement).casefold()
    normalized = " ".join(normalized.split())
    if not normalized:
        return "empty_statement"
    if _HIGH_IMPACT_DECISION.search(normalized):
        return "high_impact_decision"
    if any(pattern.search(normalized) for pattern in _PROHIBITED_ATTRIBUTE_PATTERNS):
        return "sensitive_attribute"
    if _UNCERTAIN_SENSITIVE_RELATION.search(normalized):
        return "uncertain_sensitive_relation"
    return None
