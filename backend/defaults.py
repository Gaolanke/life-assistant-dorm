"""系统默认配置。所有值都可以在网页“系统配置”里改，改完立即生效。"""
from __future__ import annotations

# key: (默认值, 分组, 说明)
DEFAULTS: dict[str, tuple[str, str, str]] = {
    # ---- 基本 ----
    "school_name": ("XX 大学", "basic", "学校名称"),
    "class_name": ("XX 学院 XX 班", "basic", "班级名称"),
    "commissary_name": ("生活委员", "basic", "汇报人署名"),
    "teacher_name": ("班主任", "basic", "接收汇报的老师"),
    "qq_report_time": ("22:40", "basic", "每晚向 QQ 群汇报的时间"),
    "auto_export_time": ("23:30", "basic", "每天自动导出 Excel 的时间"),

    "auto_backup": ("1", "jobs", "每天自动备份数据库（1 开 / 0 关）"),
    "auto_backup_time": ("03:00", "jobs", "每天自动备份数据库的时间"),
    "backup_keep": ("30", "jobs", "最多保留多少份备份，超出自动删最旧的"),    "auto_export": ("1", "basic", "是否开启每天自动导出 Excel（1 开 0 关）"),
    "absence_reasons": (
        "回家,病假,事假,外出,实习,其他",
        "basic",
        "缺席原因候选项（英文逗号分隔）",
    ),
    "site_notice": (
        "每晚 22:00 前请各宿舍长完成填报，22:40 系统自动向群内汇报。",
        "basic",
        "首页公告",
    ),

    # ---- 权限 ----
    "site_public_url": (
        "",
        "basic",
        "公开端网址（例如 https://xiaoaiyun.top；留空则自动识别）",
    ),
    "site_admin_url": (
        "",
        "basic",
        "管理端网址（例如 https://admin.xiaoaiyun.top；留空则自动识别）",
    ),
    "admin_login_note": (
        "1",
        "access",
        "管理端登录提示（账号体系已改为账号密码登录：管理员用用户名 + 密码，寝室长用宿舍号 + 密码）",
    ),

    # ---- QQ 官方机器人（QQ 开放平台：不封号、不用挂 QQ 客户端、纯 HTTP）----
    "qqbot_enabled": ("0", "qqbot", "是否启用 QQ 官方机器人推送（1 开 0 关）"),
    "qqbot_app_id": ("", "qqbot", "QQ 开放平台的 AppID"),
    "qqbot_secret": ("", "qqbot", "QQ 开放平台的 AppSecret（保密，别外传）"),
    "qqbot_groups": ("", "qqbot", "要推送的 QQ 群 openid，多个用英文逗号分隔"),
    "qqbot_api": ("https://api.sgroup.qq.com", "qqbot", "QQ 机器人 API 地址（一般不用改）"),
    "qqbot_sandbox": ("0", "qqbot", "是否用沙箱环境（1 是 0 否）"),
    "qqbot_msg_type": ("0", "qqbot", "消息类型：0 纯文本 / 2 Markdown"),
    "qqbot_public_key": ("", "qqbot", "回调签名公钥（开放平台「开发设置」里的公钥，用于校验事件来源）"),
    "qqbot_ws_enabled": ("1", "qqbot", "用 WebSocket 长连接接收事件（不需要公网 HTTPS 回调，推荐）"),

    # ---- 消息模板 ----
    "tpl_group_report": (
        "【{date} 宿舍晚归情况汇报】\n"
        "{school} {class_name}\n"
        "应查 {dorm_total} 间，已报 {reported} 间，未报 {unreported} 间\n"
        "在寝 {present} 人 / 应到 {total} 人，缺勤 {absent} 人次\n"
        "——————\n"
        "{dorm_lines}\n"
        "——————\n"
        "未填报宿舍：{missing}\n"
        "汇报人：{commissary}  {time}",
        "template",
        "每晚 QQ 群汇报模板",
    ),
    # ---- 每晚 22:00 填报提醒（发网址 + @所有人）----
    "fill_remind_enabled": ("1", "basic", "每晚定时发填报提醒（1 开 / 0 关）"),
    "fill_remind_time": ("22:00", "basic", "每晚发填报提醒的时间"),
    "fill_remind_mention_all": ("1", "basic", "填报提醒是否 @ 全体成员（1 是 / 0 否）"),
    "tpl_fill_remind": (
        "{mention}【寝室情况填报提醒】{date}\n"
        "请各位寝室长填写今晚的寝室情况（人员是否齐全、有无意外情况）。\n"
        "填报网址：{site}\n"
        "请尽快完成填报，谢谢配合！",
        "template",
        "每晚填报提醒模板（{site} 会自动换成公开端网址，{mention} 是 @所有人）",
    ),
    "tpl_dorm_pending": (
        "【待填报】{dorm} 宿舍今晚还没填报人员情况，请宿舍长尽快填写。",
        "template",
        "单宿舍催填模板",
    ),

    # ---- 定时提醒（多条，可自由增删改；JSON 存 reminders 这一个键里）----
    "reminders": (
        "",
        "remind",
        "定时提醒列表（JSON，界面化管理，不用手改）",
    ),
    "tpl_absent_dorm": (
        "⚠ {dorm} 缺 {absent_count} 人：{absent_names}{reason_text}",
        "template",
        "缺席宿舍明细行模板",
    ),
}

# 模板变量说明，前端直接展示
TEMPLATE_VARS: dict[str, str] = {
    "date": "日期 2025-05-01",
    "weekday": "星期几",
    "time": "汇报时间 22:40",
    "school": "学校名称",
    "class_name": "班级名称",
    "commissary": "汇报人署名",
    "teacher": "老师姓名",
    "dorm_total": "宿舍总间数",
    "reported": "已填报间数",
    "unreported": "未填报间数",
    "present": "在寝人数",
    "total": "应到人数",
    "absent": "缺勤人数",
    "dorm_lines": "各宿舍明细（多行）",
    "missing": "未填报宿舍（顿号分隔）",
    "missing_list": "未填报宿舍（每行一个）",
    "missing_count": "未填报宿舍数量",
    "dorm": "宿舍号（单宿舍催填用）",
    "absent_count": "该宿舍缺席人数",
    "absent_names": "该宿舍缺席人员",
    "reason_text": "缺席原因（含括号）",
    "title": "消息标题",
    "content": "消息正文",
}

# 定时提醒的预设模板：用户在「提醒推送」页一键选用，选完还能继续改
REMINDER_PRESETS: list[dict[str, object]] = [
    {
        "key": "today_fill",
        "name": "今日填报提醒",
        "mention_all": True,
        "content": (
            "{mention}【寝室情况填报提醒】{date}\n"
            "请各位寝室长填写今晚的寝室情况（人员是否齐全、有无意外情况）。\n"
            "填报网址：{site}\n"
            "请尽快完成填报，谢谢配合！"
        ),
    },
    {
        "key": "missing_list",
        "name": "谁还没填（未填名单）",
        "mention_all": False,
        "content": (
            "【填报进度】{date} {time}\n"
            "已填 {reported}/{dorm_total} 间，还有 {missing_count} 间未填报：\n"
            "{missing_list}\n"
            "请宿舍长尽快到 {site} 填报。"
        ),
    },
    {
        "key": "final_notice",
        "name": "最后通报",
        "mention_all": True,
        "content": (
            "{mention}【最后通报】{date}\n"
            "仍有 {missing_count} 间宿舍未填报：{missing}\n"
            "请这些宿舍长立即补报：{site}\n"
            "再未填报将按未归如实上报。"
        ),
    },
]
