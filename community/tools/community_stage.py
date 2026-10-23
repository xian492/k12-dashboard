"""Deterministic stage classification and relevance gating for community records.

学段按“内容里的孩子在哪个学段”判定，而不是“提到了哪个升学事件”：
资讯页侧栏的相关推荐常混入全部学段的链接，事件词匹配会把中考分析
文章错标成幼升小小升初。判定信号按强度排序：

1. 年级锚点（新初一/初二/高一/六年级…）——学生当前学段，最强信号；
2. 升学过渡词（幼升小/小升初/中考/高考）——四条过渡期各自成组，
   不并入前后学段；
3. 学校类型（标题聚焦的校名含 中学/初中/附中/小学/高中）；
4. 论坛版块（篱笆“中高考”、妈妈网“家有小学生”等站点自己的分类）；
5. 正文核心段（截掉侧栏后的前段）重复 1-3。

同级冲突取标题中更早出现者；跨级取更高优先级。标题里的“新初一”
压过正文里的“小升初”。无任何学段信号的育儿内容归“综合”。

相关性门禁同样只信标题与核心正文：标题命中教育词典即可，否则正文
需命中 ≥2 个不同教育词；标题命中生活噪声词（祝福语/供暖…）直接出局。
"""

from __future__ import annotations

import re

from community_content_cleaner import PARENT_TERMS, POLICY_TERMS, SCHOOL_TERMS


# 年级锚点：学生当前所在学段。(?<![提拉增升走跳]) 排除“提高一分”这类误配。
_GRADE_PATTERNS = [
    ("高中", re.compile(r"(?:新|(?<![一-龥提拉增升走跳]))高[一二三]")),
    ("中学", re.compile(r"新?初[一二三]|[七八九]年级")),
    ("小学", re.compile(r"[一二三四五六1-6]年级|小[五六]")),
    ("幼儿园", re.compile(r"幼儿园|托班")),
]

# 升学过渡词：四条过渡期各自成组
_TRANSITION_PATTERNS = [
    ("幼升小", re.compile(r"幼升小")),
    ("小升初", re.compile(r"小升初|XSC", re.IGNORECASE)),
    ("初升高", re.compile(r"初升高|中考|校额到校")),
    ("高考", re.compile(r"高考")),
]

# 学校类型：标题聚焦的校名后缀
_SCHOOL_TYPE_PATTERNS = [
    ("高中", re.compile(r"高中")),
    ("中学", re.compile(r"中学|初中|附中")),
    ("小学", re.compile(r"小学|附小")),
]

# 论坛版块 → 学段。只收"内容型"版块；"家有小学生/家有中学生"描述家长
# 身份而非内容学段（亲子阅读、家长会贴在里面），不映射。
BOARD_STAGE = {
    "早教幼教": "幼儿园",
    "中高考": "初升高",
    "儿童6-11": "小学",
}

# 育儿类词：无学段锚点但主题明确，归“综合”
_PARENTING_TERMS = ("家长", "亲子", "育儿", "孩子", "儿童")

# 标题命中即出局的生活噪声（资讯站的节日/市政杂文）
NOISE_TITLE_TERMS = (
    "祝福语",
    "祝福合集",
    "贺词",
    "供暖",
    "停水",
    "停电",
    "限行",
)

# 学段全词典（标题相关性判定用）
_STAGE_TERM_RE = re.compile("|".join(
    pattern.pattern for _, pattern in _GRADE_PATTERNS + _TRANSITION_PATTERNS + _SCHOOL_TYPE_PATTERNS
))
_EDUCATION_TITLE_RE = re.compile("|".join(
    [_STAGE_TERM_RE.pattern]
    + [re.escape(term) for term in POLICY_TERMS + SCHOOL_TERMS + PARENT_TERMS + _PARENTING_TERMS]
))

# 过渡期导航顺序：幼儿园 → 幼升小 → 小学 → 小升初 → 中学 → 初升高 → 高中 → 高考 → 综合
PHASE_ORDER = ("幼儿园", "幼升小", "小学", "小升初", "中学", "初升高", "高中", "高考", "综合")

# 旧标签 → 新学段（cleaner 遗留标签的兜底映射）
LEGACY_STAGE_MAP = {
    "幼儿园": "幼儿园",
    "幼升小": "幼升小",
    "小升初": "小升初",
    "XSC": "小升初",
    "中招": "小升初",
    "中考": "初升高",
    "初升高": "初升高",
    "校额到校": "初升高",
    "初中": "中学",
    "高中": "高中",
    "高考": "高考",
    "小学": "小学",
}


def _match_stages(text: str, patterns: list) -> list[tuple[int, int, str]]:
    """Collect (priority, position, stage) for every pattern hit in text."""
    hits = []
    for priority, group in enumerate(patterns):
        for stage, pattern in group:
            match = pattern.search(text or "")
            if match:
                hits.append((priority, match.start(), stage))
    return hits


def classify_stage(title: str, core_body: str = "", board: str = "") -> list[str]:
    """Return stage tags ordered by signal strength; [] means 综合或无关."""
    candidates = _match_stages(title, [_GRADE_PATTERNS, _TRANSITION_PATTERNS, _SCHOOL_TYPE_PATTERNS])
    if not candidates and board:
        board_stage = BOARD_STAGE.get(board)
        if board_stage:
            return [board_stage]
    if not candidates:
        # 正文回退只认年级锚点与过渡词；学校类型锚点仅用于标题
        # （正文顺带提到"小学/初中"不构成学段信号，育儿帖会因此误入小学档）。
        candidates = _match_stages(
            (core_body or "")[:2500],
            [_GRADE_PATTERNS, _TRANSITION_PATTERNS],
        )
    candidates.sort()
    stages = []
    for _, _, stage in candidates:
        if stage not in stages:
            stages.append(stage)
    return stages


def relevant_title(title: str) -> bool:
    """标题命中教育词典且不命中生活噪声词。"""
    text = title or ""
    if any(term in text for term in NOISE_TITLE_TERMS):
        return False
    return bool(_EDUCATION_TITLE_RE.search(text))


def relevant_article(title: str, core_body: str) -> bool:
    """资讯类：标题命中即可；标题命中噪声词直接出局，否则核心正文需
    命中 ≥2 个不同教育词。"""
    text = title or ""
    if any(term in text for term in NOISE_TITLE_TERMS):
        return False
    if relevant_title(text):
        return True
    distinct = len(set(_EDUCATION_TITLE_RE.findall((core_body or "")[:2500])))
    return distinct >= 2


def relevant_forum(title: str) -> bool:
    """论坛帖：只看标题。正文里出现一次“家长”不算教育信号。"""
    return relevant_title(title)
