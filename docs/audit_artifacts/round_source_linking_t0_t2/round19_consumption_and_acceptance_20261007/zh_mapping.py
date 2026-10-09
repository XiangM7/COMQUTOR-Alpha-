"""Fixed Chinese labels for MECHANICAL statuses (round 19). A static lookup table: no model call, no free-text generation.
A code that is not in the table is returned as-is, wrapped, so nothing is ever silently translated by guesswork.

Wording rules agreed for John's acceptance material:
  * "no source link" (NOT_PROVIDED, 714 claims) is NOT "verification failed" -- the claim never entered verification;
  * a technical fallback (timeout / response rejected by the local validator / malformed) is NOT "the model found no basis";
  * CONDITIONAL is NOT "the conclusion was proven wrong" -- it means part of the claim is not supported by the cited material.
"""

ZH = {
    "source_link_status": {
        "VALID": "已关联有效来源",
        "NOT_PROVIDED": "未关联来源（未进入内容核验，不等于核验失败）",
        "UNKNOWN_ID": "来源ID不存在",
        "CONTENT_UNAVAILABLE": "来源正文/数据不可用",
        "TIME_INVALID": "来源时间不满足证据截止条件",
    },
    "source_link_method": {
        "ORIGINAL_AGENT_MARKER_CITED": "Agent原文引用了来源/片段标记",
        "NORMALIZED_FIELD_MATCH_CANDIDATE": "确定性程序按标准化字段/数值匹配到已保存数据快照（非Agent引用）",
        "CONTENT_MATCH_CANDIDATE": "确定性程序按内容匹配到已保存来源（非Agent引用）",
        "NONE": "无",
    },
    "content_support_status": {
        "SUPPORTS": "来源内容支持该声明",
        "CONDITIONAL": "部分/有条件支持（声明含未被所引材料支持的部分，不等于结论被证伪）",
        "BACKGROUND": "仅为背景信息，不构成支持",
        "OPPOSES": "来源内容与声明相反",
        "PENDING_REVIEW": "内容核验未得出结论",
        "NOT_APPLICABLE": "不适用（未关联来源）",
    },
    "content_support_method": {
        "LLM_CONTENT_SUPPORT_VERIFIED": "模型内容核验（content_support.llm.v2.1）",
        "UNVERIFIED_OFFLINE_CONTENT_MATCH": "离线内容匹配（未经模型核验）",
        "ORIGINAL_AGENT_CITED_UNVERIFIED_SUPPORT": "Agent自行引用（未经核验）",
        "AUTOMATED_DATA_FACT_VERIFIED": "自动数据事实核验（确定性程序）",
        "AUTOMATED_DERIVED_CALC_VERIFIED": "自动派生计算核验（确定性程序）",
        "HUMAN_REVIEWED": "人工审核",
        "NOT_LINKED": "未关联来源，无核验",
    },
    "verification_fallback": {
        "timeout": "核验请求超时（技术性回退，不代表模型认为没有依据）",
        "quote_or_data_not_found": "模型给出的引文/数据位置未能在允许材料中定位，响应被本地校验拒绝（技术性回退，不代表模型认为没有依据）",
        "malformed_response": "模型响应格式不合规（技术性回退，不代表模型认为没有依据）",
    },
    "llm_status": {
        "SUPPORTS": "模型判断：支持",
        "CONDITIONAL": "模型判断：有条件支持",
        "BACKGROUND": "模型判断：背景",
        "OPPOSES": "模型判断：相反",
        "INSUFFICIENT": "模型判断：所给材料不足以判断（模型已作出判断，非技术回退）",
    },
    "support_basis": {
        "DIRECT_FACT": "直接事实",
        "GROUNDED_INFERENCE": "有依据的推论",
        "DERIVED_CALCULATION": "派生计算",
    },
    "claim_quality": {
        "analytical": "分析性声明",
        "context_only": "背景/事实陈述（非分析性，不作为Alpha证据）",
    },
    "eligibility": {
        "ELIGIBLE": "具备正式证据资格",
        "SOURCE_LINK_NOT_VALID": "未关联有效来源",
        "NOT_REVIEWED": "核验方法不具资格或核验未完成",
        "SUPPORT_STATUS_NOT_RESOLVED": "核验已执行但结论不是“支持”（有条件/背景/材料不足）",
        "REVIEW_CLAIM_MISMATCH": "核验记录与声明不一致",
        "CONTENT_VERSION_CHANGED_SINCE_REVIEW": "来源内容在核验后发生变化",
        "SOURCE_NOT_RESOLVABLE": "来源无法解析",
        "SOURCE_OPPOSES_CLAIM": "来源内容与声明相反",
        "DISCLOSURE_TIME_UNKNOWN": "披露/可用时间未知",
        "REVIEW_SOURCE_NOT_LINKED_TO_CLAIM": "核验所用来源不在该声明的引用之内",
        "AVAILABILITY_NOT_BEFORE_EVIDENCE_CUTOFF": "来源获得时间不早于证据截止时间",
    },
    "time_basis": {
        "PUBLISHED_AT": "已知发布时间（published_at）",
        "REGISTRY_WRITE_TIME_UPPER_BOUND": "published_at未知；以来源注册表写入时间作为可用时间上界（REGISTRY_WRITE_TIME_UPPER_BOUND，不是披露日期）",
        "UNKNOWN": "时间未知",
        "NOT_APPLICABLE": "不适用（未关联来源）",
    },
    "match_status": {
        "matched": "已匹配Alpha",
        "no_match": "无匹配Alpha",
        "unavailable": "分类未获得结果（请求超时，未重试）",
    },
    "classifier_status": {
        "llm_selected": "模型选择了一个Alpha",
        "llm_none": "模型判定没有Alpha实质相关",
        "provider_timeout": "分类请求超时，无模型结果",
    },
    "mapper_override": {
        "alpha_positive_requirement_override": "模型选择A001，但映射器的A001正向要求语义门控未满足，改判为无匹配",
        "alpha_specific_invalidation_override": "模型选择A001，但映射器的A001专属否证规则命中，改判为无匹配",
        "none": "无",
    },
    "relation": {
        "activation": "支持性关系（activation，文本规则默认值）",
        "conditional": "条件性关系",
        "mixed": "混合关系",
        "mention": "仅提及/否定语境（mention）",
        "invalidation": "否证",
        "risk_relief": "风险缓解",
        "unknown": "未知",
        "n/a": "不适用（未匹配Alpha）",
    },
    "assertion_status": {
        "asserted": "断言",
        "conditional": "条件性",
        "negated": "含否定词",
        "mixed": "混合",
        "unknown": "未知",
    },
    "evidence_stance": {
        "supports_alpha": "支持该Alpha",
        "opposes_alpha": "反对该Alpha",
        "mentions_alpha": "仅涉及该Alpha，未表态",
        "neutral_background": "背景",
        "supports_counter_alpha": "支持该Alpha的对立Alpha",
        "n/a": "不适用",
    },
    "not_scored": {
        "IN_OFFICIAL_POOL": "已进入正式证据池",
        "CLASSIFICATION_UNAVAILABLE": "分类请求超时，未获得模型判断",
        "MODEL_NONE": "模型判定没有Alpha实质相关",
        "MAPPER_GATE_OVERRIDE": "模型选择后被映射器门控改判为无匹配",
        "VERIFIED_GATE_SOURCE_LINK_NOT_VALID": "已匹配，但未关联有效来源，不进入正式池",
        "VERIFIED_GATE_NOT_REVIEWED": "已匹配，但内容核验未完成或方法不具资格，不进入正式池",
        "VERIFIED_GATE_SUPPORT_STATUS_NOT_RESOLVED": "已匹配，但内容核验结论不是“支持”，不进入正式池",
        "VERIFIED_GATE_SOURCE_OPPOSES_CLAIM": "已匹配，但来源内容与声明相反，不进入正式池",
        "VERIFIED_GATE_OTHER": "已匹配，但未通过已验证证据资格门",
        "NON_ANALYTICAL_QUALITY": "已匹配且已验证，但声明为非分析性（背景/事实陈述），不作为Alpha证据",
        "RELATION_NOT_SUPPORTING": "已匹配，但关系为提及/否证/风险缓解（文本规则），不属于支持性证据",
        "ASSERTION_NEGATED": "已匹配，但含否定词（文本规则），不计入证据",
        "ROLE_OR_GROUPING_GATE": "已匹配，被证据角色/分组规则排除",
    },
    "yes_no": {True: "是", False: "否", None: "未评估"},
}


def zh(category, code, default=None):
    table = ZH.get(category, {})
    if code in table:
        return table[code]
    if default is not None:
        return default
    return f"{code}（无固定中文映射）" if code not in (None, "") else ""
